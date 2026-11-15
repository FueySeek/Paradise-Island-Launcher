/* 校验多语言完整性：node tools/check_i18n.js */
const fs = require("fs");
const path = require("path");

global.window = {};
const root = path.join(__dirname, "..");
["static/js/i18n.js", "static/js/i18n-extra.js", "static/js/i18n-extra2.js"].forEach((f) => {
  const file = path.join(root, f);
  new Function("window", fs.readFileSync(file, "utf8"))(global.window);
});

const I18N = global.window.I18N;
const LANGS = Object.keys(I18N);
const base = Object.keys(I18N["zh-CN"]);

const appSrc = fs.readFileSync(path.join(root, "static/js/app.js"), "utf8");
const htmlSrc = fs.readFileSync(path.join(root, "static/index.html"), "utf8");

const used = new Set();
for (const m of appSrc.matchAll(/\bt\(\s*"([a-zA-Z0-9_.]+)"/g)) {
  if (!m[1].endsWith(".")) used.add(m[1]);
}
for (const m of htmlSrc.matchAll(/data-i18n(?:-ph)?="([a-zA-Z0-9_.]+)"/g)) used.add(m[1]);
const stageKeys = ["prepare", "meta", "client", "libraries", "assets", "java", "loader", "done", "error"]
  .map((s) => "stage." + s);
const loaderKeys = ["vanilla", "forge", "neoforge", "fabric", "quilt"].map((s) => "loader." + s);
[...stageKeys, ...loaderKeys].forEach((k) => used.add(k));

let errors = 0;
for (const lang of LANGS) {
  const dict = I18N[lang];
  const missingInLang = base.filter((k) => !(k in dict));
  if (missingInLang.length) {
    errors += missingInLang.length;
    console.log(`[${lang}] 缺少 ${missingInLang.length} 个键:`, missingInLang.join(", "));
  }
  const missingUsed = [...used].filter((k) => !(k in dict));
  if (missingUsed.length) {
    errors += missingUsed.length;
    console.log(`[${lang}] 使用了未定义的键:`, missingUsed.join(", "));
  }
}
const unused = base.filter((k) => !used.has(k));
console.log(`语言数: ${LANGS.length}，基准键数: ${base.length}，使用键数: ${used.size}`);
if (unused.length) console.log("未使用的键:", unused.join(", "));
if (errors === 0) console.log("OK: 所有语言键完整");
process.exit(errors === 0 ? 0 : 1);
