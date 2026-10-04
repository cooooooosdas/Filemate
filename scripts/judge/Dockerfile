FROM m.daocloud.io/docker.io/library/alpine@sha256:5291449c3df73caf6ed85e649dec1b9e818b39a5d8c871e97afc13e9cd5e8fa8
RUN sed -i 's/dl-cdn.alpinelinux.org/mirrors.aliyun.com/g' /etc/apk/repositories && apk add --no-cache g++=14.2.0-r6
RUN apk add --no-cache linux-headers=6.14.2-r0
COPY runner.c /tmp/runner.c
RUN gcc -O2 -Wall -Wextra -Werror /tmp/runner.c -o /usr/local/bin/filemate-runner && rm /tmp/runner.c
USER 65534:65534
WORKDIR /tmp
