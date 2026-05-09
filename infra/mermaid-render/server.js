const http = require("http");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawn } = require("child_process");

const PORT = Number(process.env.PORT || 3000);
const MAX_BODY_BYTES = Number(process.env.MAX_BODY_BYTES || 262144);
const RENDER_TIMEOUT_MS = Number(process.env.RENDER_TIMEOUT_MS || 20000);

function send(res, status, payload) {
  const body = JSON.stringify(payload);
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": Buffer.byteLength(body),
  });
  res.end(body);
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let size = 0;
    req.on("data", (chunk) => {
      size += chunk.length;
      if (size > MAX_BODY_BYTES) {
        reject(new Error("request body too large"));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
    req.on("error", reject);
  });
}

function renderMermaid(source) {
  return new Promise((resolve, reject) => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "mmd-"));
    const input = path.join(dir, "chart.mmd");
    const output = path.join(dir, "chart.svg");
    const config = path.join(dir, "puppeteer.json");
    fs.writeFileSync(input, source, "utf8");
    fs.writeFileSync(config, JSON.stringify({ args: ["--no-sandbox", "--disable-setuid-sandbox"] }), "utf8");

    const child = spawn("mmdc", ["-i", input, "-o", output, "-p", config, "-b", "transparent"], {
      stdio: ["ignore", "pipe", "pipe"],
    });
    const timer = setTimeout(() => {
      child.kill("SIGKILL");
      reject(new Error("render timeout"));
    }, RENDER_TIMEOUT_MS);

    let stderr = "";
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString("utf8");
    });
    child.on("error", (error) => {
      clearTimeout(timer);
      reject(error);
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      try {
        if (code !== 0) {
          reject(new Error(stderr || `mmdc exited with ${code}`));
          return;
        }
        resolve(fs.readFileSync(output, "utf8"));
      } finally {
        fs.rmSync(dir, { recursive: true, force: true });
      }
    });
  });
}

const server = http.createServer(async (req, res) => {
  if (req.method === "GET" && req.url === "/health") {
    send(res, 200, { status: "ok" });
    return;
  }
  if (req.method !== "POST" || req.url !== "/render") {
    send(res, 404, { detail: "not found" });
    return;
  }
  try {
    const raw = await readBody(req);
    const payload = JSON.parse(raw);
    const source = String(payload.source || "");
    if (!source.trim()) {
      send(res, 400, { detail: "source is required" });
      return;
    }
    const svg = await renderMermaid(source);
    send(res, 200, { svg });
  } catch (error) {
    send(res, 400, { detail: error.message || "render failed" });
  }
});

server.listen(PORT, "0.0.0.0");
