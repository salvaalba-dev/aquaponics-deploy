async function wakeAndCheck(cfg) {
  // AU deployment binding only; the shared controller contains no persona names.
  if (!cfg || cfg.chrome_service !== "chrome-alma" || cfg.cdp_port !== 18802 ||
      typeof process.getuid !== "function" || process.getuid() !== 1059) {
    return { ok: false, error: "UNEXPECTED_BROWSER_BINDING" };
  }
  try {
    // Validate the root-managed binding even if Chrome is already running.
    require("node:child_process").execFileSync(
      "/usr/bin/python3",
      ["-I", "/usr/local/libexec/persona_service_control.py", "client",
       "--config", "/etc/persona-service-control/alma-browser.json"],
      { timeout: 40000, stdio: "ignore" });
  } catch (e) {
    return { ok: false, error: "SERVICE_CONTROL_UNAVAILABLE" };
  }
  // This checks browser health, not application login or query approval.
  return await checkChrome(cfg.cdp_port);
}
