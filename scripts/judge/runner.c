/* The parent owns timing and evidence; the student's child cannot fork or signal it. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/filter.h>
#include <linux/seccomp.h>
#include <stddef.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define DENY(n) BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K, (n), 0, 1), BPF_STMT(BPF_RET|BPF_K, SECCOMP_RET_ERRNO|EPERM)
static long millis(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec * 1000 + t.tv_nsec / 1000000;
}
static long address_size_kb(pid_t child) {
    char path[64];
    snprintf(path, sizeof(path), "/proc/%ld/statm", (long)child);
    FILE *statistics = fopen(path, "r");
    if (!statistics) return 0;
    long pages = 0;
    int parsed = fscanf(statistics, "%ld", &pages);
    fclose(statistics);
    /* statm has no process name or user-controlled text; gVisor need not expose VmPeak. */
    return parsed == 1 && pages > 0 ? pages * (sysconf(_SC_PAGESIZE)/1024) : 0;
}
static int restrict_child(void) {
    struct sock_filter instructions[] = {
        BPF_STMT(BPF_LD|BPF_W|BPF_ABS, offsetof(struct seccomp_data, arch)),
        BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K, 0xc000003e, 1, 0),
        BPF_STMT(BPF_RET|BPF_K, SECCOMP_RET_KILL_PROCESS),
        BPF_STMT(BPF_LD|BPF_W|BPF_ABS, offsetof(struct seccomp_data, nr)),
        BPF_JUMP(BPF_JMP|BPF_JGE|BPF_K, 0x40000000, 0, 1),
        BPF_STMT(BPF_RET|BPF_K, SECCOMP_RET_KILL_PROCESS),
        DENY(SYS_clone), DENY(SYS_clone3), DENY(SYS_fork), DENY(SYS_vfork),
        DENY(SYS_socket), DENY(SYS_socketpair), DENY(SYS_kill), DENY(SYS_tkill), DENY(SYS_tgkill),
        DENY(SYS_rt_sigqueueinfo), DENY(SYS_rt_tgsigqueueinfo),
        DENY(SYS_pidfd_open), DENY(SYS_pidfd_getfd), DENY(SYS_pidfd_send_signal),
        DENY(SYS_ptrace), DENY(SYS_process_vm_readv), DENY(SYS_process_vm_writev),
        DENY(SYS_mount), DENY(SYS_umount2), DENY(SYS_unshare), DENY(SYS_setns),
        DENY(SYS_bpf), DENY(SYS_perf_event_open), DENY(SYS_userfaultfd),
        BPF_STMT(BPF_RET|BPF_K, SECCOMP_RET_ALLOW)
    };
    struct sock_fprog policy = {sizeof(instructions)/sizeof(instructions[0]), instructions};
    return prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) || prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, &policy);
}
int main(int argc, char **argv) {
    if (argc != 3) return 125;
    long limit = strtol(argv[1], NULL, 10), memory = strtol(argv[2], NULL, 10);
    if (limit < 100 || limit > 10000 || memory < 16 || memory > 256) return 125;
    if (!address_size_kb(getpid())) return 125;
    int control[2];
    if (pipe2(control, O_CLOEXEC) || prctl(PR_SET_DUMPABLE, 0)) return 125;
    long started = millis();
    pid_t child = fork();
    if (child < 0) return 125;
    if (child == 0) {
        close(control[0]);
        /* The supervisor observes the declared limit; the hard VM guard allows
           only 16 MiB of detection headroom. Sentry has a separate cgroup reserve. */
        struct rlimit address = {(rlim_t)(memory+16)*1024*1024, (rlim_t)(memory+16)*1024*1024};
        struct rlimit files = {8*1024*1024, 8*1024*1024}, core = {0, 0};
        struct rlimit cpu = {(rlim_t)(limit/1000+1), (rlim_t)(limit/1000+1)};
        if (setrlimit(RLIMIT_AS, &address) || setrlimit(RLIMIT_FSIZE, &files) ||
            setrlimit(RLIMIT_CORE, &core) || setrlimit(RLIMIT_CPU, &cpu) || restrict_child()) {
            write(control[1], "E", 1); _exit(125);
        }
        char *arguments[] = {"/program", NULL};
        execv(arguments[0], arguments);
        write(control[1], "E", 1);
        _exit(125);
    }
    close(control[1]);
    int status = 0, timeout = 0, memory_exceeded = 0, observation_failed = 0, observation_misses = 0;
    long peak_address = 0;
    struct rusage usage = {0};
    while (1) {
        long current_peak = address_size_kb(child);
        if (current_peak > peak_address) peak_address = current_peak;
        pid_t result = wait4(child, &status, WNOHANG, &usage);
        if (result == child) {
            memory_exceeded = peak_address > memory*1024 || usage.ru_maxrss > memory*1024;
            break;
        }
        if (result < 0 && errno != EINTR) return 125;
        /* A process shutting down may have released its mm before wait4 can reap it. */
        observation_misses = current_peak ? 0 : observation_misses + 1;
        if (observation_misses >= 10 && result == 0) {
            observation_failed = 1;
            kill(child, SIGKILL);
            if (wait4(child, &status, 0, &usage) != child) return 125;
            break;
        }
        if (peak_address > memory*1024) {
            memory_exceeded = 1;
            kill(child, SIGKILL);
            if (wait4(child, &status, 0, &usage) != child) return 125;
            break;
        }
        if (millis() - started >= limit) {
            timeout = 1;
            kill(child, SIGKILL);
            if (wait4(child, &status, 0, &usage) != child) return 125;
            break;
        }
        struct timespec delay = {0, 2000000};
        nanosleep(&delay, NULL);
    }
    int exit_code = WIFEXITED(status) ? WEXITSTATUS(status) : 128 + WTERMSIG(status);
    char setup_error;
    int failed = read(control[0], &setup_error, 1) > 0 || observation_failed;
    close(control[0]);
    fprintf(stderr, "\nFILEMATE_RESULT={\"exit_code\":%d,\"elapsed_ms\":%ld,\"peak_memory_bytes\":%ld,\"peak_address_bytes\":%ld,\"reason\":\"%s\"}\n",
            exit_code, millis()-started, usage.ru_maxrss*1024, peak_address*1024,
            failed ? "sandbox_error" : memory_exceeded ? "memory_limit" : timeout ? "timeout" : "");
    return 0;
}
