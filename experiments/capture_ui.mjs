/**
 * 第 6 章前端界面自动化截图脚本（基于 Puppeteer + 本机 Chrome）。
 * 输出：
 *   thesis/figs/fig6_1_im_chat.png   IM 模拟器群聊界面（含多模态图片消息与回复引用）
 *   thesis/figs/fig6_2_qa_card.png   知识助手“小知”单聊问答与可点击引用来源卡片
 *   thesis/figs/fig6_3_admin.png     管理后台（统计卡片、增量同步操作与 MKU 列表）
 */
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import puppeteer from '../thesis/node_modules/puppeteer/lib/puppeteer/puppeteer.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FIGS = path.resolve(__dirname, '..', 'thesis', 'figs');
const BASE_URL = process.env.EIM_URL || 'http://127.0.0.1:8000';
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function waitImages(page) {
  await page.evaluate(async () => {
    const imgs = Array.from(document.querySelectorAll('img'));
    await Promise.all(
      imgs.map((img) =>
        img.complete
          ? Promise.resolve()
          : new Promise((res) => {
              img.onload = res;
              img.onerror = res;
            })
      )
    );
  });
}

async function main() {
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 2 });

  await page.goto(BASE_URL, { waitUntil: 'networkidle2' });
  await page.waitForSelector('.convs .conv', { timeout: 15000 });

  // 1) fig6_1_im_chat.png: 后端研发群（含截图消息与引用回复）
  await page.evaluate(() => {
    const items = Array.from(document.querySelectorAll('.convs .conv'));
    const target = items.find((el) => el.textContent.includes('后端研发群'));
    if (target) target.click();
  });
  await page.waitForSelector('.msgs .msg', { timeout: 15000 });
  await sleep(600);
  await waitImages(page);
  await page.evaluate(() => {
    const el = document.getElementById('m_F002_m00') || document.querySelector('.msgs .msg');
    if (el) el.scrollIntoView({ block: 'center' });
  });
  await sleep(500);
  await page.screenshot({ path: path.join(FIGS, 'fig6_1_im_chat.png') });
  console.log('saved fig6_1_im_chat.png');

  // 2) fig6_2_qa_card.png: 小知单聊实时提问 + 引用卡片
  await page.click('.convs .conv.bot');
  await page.waitForFunction(
    () => document.querySelector('.chat-head')?.textContent?.includes('小知'),
    { timeout: 10000 }
  );
  await sleep(400);
  const qText = '8 月 11 日用户中心刷新 token 失败的错误码是什么？该错误的根因是什么？';
  await page.evaluate((text) => {
    const inp = document.querySelector('.composer input.el-input__inner');
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
    setter.call(inp, text);
    inp.dispatchEvent(new Event('input', { bubbles: true }));
  }, qText);
  await page.focus('.composer input.el-input__inner');
  await page.keyboard.press('Enter');

  // 等待回答与来源卡片出现，且 thinking 消失
  await page.waitForFunction(
    () => !document.querySelector('.thinking') && document.querySelectorAll('.cites .cite').length > 0,
    { timeout: 120000 }
  );
  await sleep(500);
  await page.evaluate(() => {
    const box = document.querySelector('.msgs');
    if (box) box.scrollTop = box.scrollHeight;
  });
  await sleep(400);
  await page.screenshot({ path: path.join(FIGS, 'fig6_2_qa_card.png') });
  console.log('saved fig6_2_qa_card.png');

  // 3) fig6_3_admin.png: 管理后台（统计卡片 + 知识单元表格）
  await page.evaluate(() => {
    const radios = Array.from(document.querySelectorAll('.topbar .el-radio-button'));
    const adminBtn = radios.find((el) => el.textContent.includes('管理后台'));
    if (adminBtn) adminBtn.click();
  });
  await page.waitForSelector('.admin .stats .el-card', { timeout: 15000 });
  await page.waitForSelector('.admin .el-table__row', { timeout: 15000 });
  await sleep(600);
  await page.screenshot({ path: path.join(FIGS, 'fig6_3_admin.png') });
  console.log('saved fig6_3_admin.png');

  await browser.close();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
