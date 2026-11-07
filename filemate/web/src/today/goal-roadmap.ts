import type { ReverseGoalTask } from "../services/api";

const stages = [
  {
    key: "prepare",
    label: "准备",
    ids: ["import-source", "review-source", "build-study-plan"],
  },
  {
    key: "practice",
    label: "练习",
    ids: [
      "baseline-quiz",
      "clear-due-wrong",
      "explain-wrong-aloud",
      "baseline-interview",
    ],
  },
  { key: "review", label: "复盘", ids: ["review-evidence"] },
  { key: "other", label: "其他行动", ids: [] },
] as const;

export function groupGoalTasks(tasks: ReverseGoalTask[], today: string) {
  return stages
    .map((stage) => {
      const members = tasks.filter((task) => {
        const found = stages.find((candidate) =>
          (candidate.ids as readonly string[]).includes(task.task_id),
        );
        return (found?.key ?? "other") === stage.key;
      });
      const overdue = members.filter((task) => {
        const date = task.due_date;
        if (
          task.status !== "pending" ||
          typeof date !== "string" ||
          !/^\d{4}-\d{2}-\d{2}$/.test(date)
        )
          return false;
        const parsed = new Date(date + "T00:00:00Z");
        return (
          Number.isFinite(parsed.getTime()) &&
          parsed.toISOString().slice(0, 10) === date &&
          date < today
        );
      }).length;
      return {
        key: stage.key,
        label: stage.label,
        tasks: members,
        overdue,
        completed: members.filter((task) => task.status === "completed").length,
      };
    })
    .filter((stage) => stage.tasks.length > 0);
}
