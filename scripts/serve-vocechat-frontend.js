#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");
const http = require("http");
const https = require("https");
const { URL } = require("url");

const host = process.env.HOST || "0.0.0.0";
const port = Number(process.env.PORT || "7925");
const appRoot = process.env.VOCECHAT_WEB_ROOT || "/root/devstack/workspace/apps/vocechat-web";
const staticDir = path.join(appRoot, "build");
const target = new URL(process.env.VOCECHAT_API_TARGET || "http://127.0.0.1:7922");
const proxyClient = target.protocol === "https:" ? https : http;

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".gif": "image/gif",
  ".webp": "image/webp",
  ".ico": "image/x-icon",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".ttf": "font/ttf",
  ".map": "application/json; charset=utf-8",
  ".txt": "text/plain; charset=utf-8",
};

function setCors(res) {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "*");
  res.setHeader("Access-Control-Allow-Headers", "*");
}

function proxyApi(req, res) {
  const proxyPath = req.url || "/";
  const options = {
    protocol: target.protocol,
    hostname: target.hostname,
    port: target.port || (target.protocol === "https:" ? 443 : 80),
    method: req.method,
    path: proxyPath,
    headers: {
      ...req.headers,
      host: target.host,
    },
  };

  const proxyReq = proxyClient.request(options, (proxyRes) => {
    res.writeHead(proxyRes.statusCode || 502, proxyRes.headers);
    proxyRes.pipe(res);
  });

  proxyReq.on("error", (err) => {
    setCors(res);
    res.writeHead(502, { "Content-Type": "application/json; charset=utf-8" });
    res.end(
      JSON.stringify({
        message: "frontend proxy error",
        detail: err.message,
      })
    );
  });

  req.pipe(proxyReq);
}

function safePathname(urlPath) {
  try {
    const decoded = decodeURIComponent(urlPath.split("?")[0]);
    const clean = decoded.replace(/^\/+/, "");
    const resolved = path.resolve(staticDir, clean);
    if (!resolved.startsWith(staticDir)) {
      return path.join(staticDir, "index.html");
    }
    return resolved;
  } catch {
    return path.join(staticDir, "index.html");
  }
}

function sendFile(filePath, res) {
  fs.readFile(filePath, (err, data) => {
    if (err) {
      res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
      res.end("Not Found");
      return;
    }
    const ext = path.extname(filePath).toLowerCase();
    const type = MIME[ext] || "application/octet-stream";
    res.writeHead(200, { "Content-Type": type });
    res.end(data);
  });
}

function serveStatic(req, res) {
  const urlPath = req.url || "/";
  let filePath = safePathname(urlPath);

  if (urlPath === "/" || filePath.endsWith(path.sep)) {
    filePath = path.join(staticDir, "index.html");
  }

  fs.stat(filePath, (err, stat) => {
    if (!err && stat.isFile()) {
      sendFile(filePath, res);
      return;
    }
    sendFile(path.join(staticDir, "index.html"), res);
  });
}

if (!fs.existsSync(path.join(staticDir, "index.html"))) {
  console.error(`[vocechat-web] build not found: ${staticDir}`);
  process.exit(1);
}

const server = http.createServer((req, res) => {
  if (!req.url) {
    res.writeHead(400, { "Content-Type": "text/plain; charset=utf-8" });
    res.end("Bad Request");
    return;
  }
  if (req.url.startsWith("/api")) {
    proxyApi(req, res);
    return;
  }
  serveStatic(req, res);
});

server.listen(port, host, () => {
  console.log(`[vocechat-web] serving ${staticDir} on http://${host}:${port}`);
  console.log(`[vocechat-web] proxy /api -> ${target.origin}`);
});

