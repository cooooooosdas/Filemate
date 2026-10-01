import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { chromium } from "playwright";

const base = process.env.FILEMATE_WEB_URL || "http://127.0.0.1:5197";
const api = process.env.FILEMATE_API_URL || "http://127.0.0.1:8026";
const out = path.resolve(
  process.env.FILEMATE_EVIDENCE_DIR || "_working/acceptance/state",
);
assert.ok(out.startsWith(path.join(process.cwd(), "_working") + path.sep));
fs.mkdirSync(out, { recursive: true });
const browser = await chromium.launch({ channel: "msedge", headless: true });
const context = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
});
const page = await context.newPage();
page.setDefaultTimeout(10000);
const results = [],
  errors = [],
  stamp = crypto.randomUUID();
page.on("pageerror", (error) => errors.push(String(error)));
async function request(method, url, body) {
  const response = await context.request.fetch(api + url, {
    method,
    data: body,
  });
  assert.equal(response.status(), 200, await response.text());
  return (await response.json()).data;
}
async function check(name, run) {
  try {
    await run();
    results.push({ name, passed: true });
    console.log("PASS", name);
  } catch (error) {
    results.push({ name, passed: false, error: String(error) });
    console.log("FAIL", name, String(error));
  }
}
const heading = (title) =>
  page.getByRole("heading", { name: title, exact: true });
const button = (title) =>
  page.getByRole("button", { name: title, exact: true });
const dialogButton = (title) =>
  page.getByRole("dialog").getByRole("button", { name: title, exact: true });
const fixture = (title) => ({
  company: "合成状态回归",
  title,
  region: "本地测试",
  industry: "软件",
  employment: "用户自定义",
  source: "合成回归，不是实际招聘",
  source_url: "",
  source_kind: "user_import",
  collected_at: new Date().toISOString(),
  published_at: "",
  description: "岗位要求：理解数据结构与数据库的基本概念。",
  requirements: [
    { label: "数据结构", category: "knowledge", evidence: "数据结构" },
    { label: "数据库", category: "knowledge", evidence: "数据库" },
  ],
});
const ids = [];
try {
  const alpha = await request("POST", "/api/career/positions", {
    position: fixture("状态回归甲"),
    confirmed: true,
    request_key: "alpha_" + stamp,
  });
  const beta = await request("POST", "/api/career/positions", {
    position: fixture("状态回归乙"),
    confirmed: true,
    request_key: "beta_" + stamp,
  });
  ids.push(alpha.position_id, beta.position_id);
  await check(
    "position selection and browser back restore matching role",
    async () => {
      await page.goto(base + "/career?position=" + alpha.position_id);
      await heading("状态回归甲").waitFor();
      await page
        .locator(".position-row")
        .filter({ hasText: "状态回归乙" })
        .click();
      await heading("状态回归乙").waitFor();
      await page.goBack();
      await heading("状态回归甲").waitFor();
      assert.equal(
        new URL(page.url()).searchParams.get("position"),
        alpha.position_id,
      );
    },
  );
  await check(
    "training history back restores snapshot without answer leakage between rounds",
    async () => {
      const written = [];
      for (let index = 0; index < 2; index++)
        written.push(
          await request(
            "POST",
            `/api/career/positions/${alpha.position_id}/trainings`,
            {
              kind: "written",
              confirmed: true,
              expected_revision: alpha.revision,
              request_key: `round_${index}_${stamp}`,
            },
          ),
        );
      await page.goto(
        `${base}/career?position=${alpha.position_id}&training=${written[0].training_id}`,
      );
      await page.locator(".training-detail").waitFor();
      await page.locator('input[name=stack][value="1"]').check();
      await page.locator(".history-row").first().click();
      await page.waitForURL(
        (url) => url.searchParams.get("training") === written[1].training_id,
      );
      assert.equal(await page.locator("input[name=stack]:checked").count(), 0);
      await page.goBack();
      await page.waitForURL(
        (url) => url.searchParams.get("training") === written[0].training_id,
      );
      await page.locator(".training-detail").waitFor();
      assert.equal(
        await page.evaluate(() =>
          new URL(location.href).searchParams.get("training"),
        ),
        written[0].training_id,
      );
    },
  );
  await check(
    "unsaved draft navigation cancel preserves draft then explicit discard leaves",
    async () => {
      await page.goto(base + "/career?position=" + alpha.position_id);
      await heading("状态回归甲").waitFor();
      await button("导入岗位").click();
      await page
        .getByLabel("企业名称", { exact: true })
        .fill("未保存的合成草稿");
      await page.getByRole("link", { name: "学习工作区", exact: true }).click();
      await dialogButton("继续核对").click();
      assert.equal(
        await page.getByLabel("企业名称", { exact: true }).inputValue(),
        "未保存的合成草稿",
      );
      await page.getByRole("link", { name: "学习工作区", exact: true }).click();
      await dialogButton("丢弃草稿").click();
      await page.waitForURL("**/ai-tools");
    },
  );
  await check(
    "career knowledge evidence deep-link opens original node and confirmed learning plan",
    async () => {
      const imported = await context.request.post(api + "/knowledge/import", {
        multipart: {
          file: {
            name: "合成求职状态回归.txt",
            mimeType: "text/plain",
            buffer: Buffer.from(
              "数据结构：用于组织和存储数据的方法。\n数据库：按结构组织的数据集合。\n合成测试批次 " +
                stamp,
            ),
          },
        },
      });
      assert.equal(imported.status(), 200);
      const source = (await imported.json()).data;
      const batch = await request("POST", "/api/knowledge-graph/drafts", {
        source_id: source.source_id,
        mode: "local",
      });
      await request(
        "POST",
        `/api/knowledge-graph/batches/${batch.batch_id}/confirm`,
        {},
      );
      const graph = await request("GET", "/api/knowledge-graph");
      const node = graph.nodes.find(
        (n) => n.source_id === source.source_id && n.label === "数据库",
      );
      assert.ok(node);
      await page.goto(base + "/career?position=" + alpha.position_id);
      const link = page
        .locator(`a[href*="node=${encodeURIComponent(node.id)}"]`)
        .first();
      await link.click();
      await page
        .locator(".evidence-panel h2")
        .filter({ hasText: "数据库" })
        .waitFor();
      await button("预览学习路径").click();
      await page.locator(".plan-preview").waitFor();
      await button("确认加入学习计划").click();
      await page.locator(".saved-plan").waitFor();
      const latest = await request("GET", "/api/knowledge-graph");
      assert.equal(latest.plans.length, graph.plans.length + 1);
      const plan = latest.plans.find(
        (p) =>
          p.source_id === source.source_id &&
          !graph.plans.some((old) => old.plan_id === p.plan_id),
      );
      assert.ok(plan);
      const record = await request("GET", "/study-plans/" + plan.plan_id);
      assert.ok(record);
      await button("撤销此计划").click();
      await button("恢复此计划").waitFor();
      assert.equal(
        (await request("GET", "/study-plans/" + plan.plan_id)).status,
        "archived",
      );
      await button("恢复此计划").click();
      await button("撤销此计划").waitFor();
      assert.equal(
        (await request("GET", "/study-plans/" + plan.plan_id)).status,
        "active",
      );
      await page.screenshot({
        path: path.join(out, "career-learning-plan.png"),
      });
    },
  );
  assert.deepEqual(errors, []);
} finally {
  for (const id of ids) {
    const preview = await request(
      "GET",
      `/api/career/positions/${id}/delete-preview`,
    );
    await request("DELETE", `/api/career/positions/${id}`, {
      confirmed: true,
      confirmation_token: preview.confirmation_token,
    });
  }
  await browser.close();
}
const summary = {
  sample_kind: "synthetic_state_regression",
  passed: results.filter((r) => r.passed).length,
  total: results.length,
  errors,
  results,
};
fs.writeFileSync(
  path.join(out, "summary.json"),
  JSON.stringify(summary, null, 2),
);
console.log(JSON.stringify(summary));
if (summary.passed !== summary.total || errors.length) process.exitCode = 1;
