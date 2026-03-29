const { createProxyMiddleware } = require("http-proxy-middleware");

module.exports = function setupProxy(app) {
  const port = process.env.REACT_APP_SERVER_PORT || "7922";
  const target = (process.env.REACT_APP_SERVER_ORIGIN || `http://127.0.0.1:${port}`).replace(
    /\/$/,
    ""
  );

  app.use(
    "/api",
    createProxyMiddleware({
      target,
      changeOrigin: true,
      ws: true,
      logLevel: "debug",
      onProxyReq(proxyReq, req) {
        const ip = req.ip || req.socket?.remoteAddress || "unknown";
        console.log(`[proxy][req] ${req.method} ${req.originalUrl} from ${ip} -> ${target}`);
      },
      onProxyRes(proxyRes, req) {
        console.log(`[proxy][res] ${req.method} ${req.originalUrl} <= ${proxyRes.statusCode}`);
      },
      onError(err, req) {
        console.error(`[proxy][err] ${req.method} ${req.originalUrl}: ${err.message}`);
      },
    })
  );
};

