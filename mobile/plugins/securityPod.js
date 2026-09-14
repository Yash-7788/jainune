const POD_LINE = "  pod 'JainuneSecurityModule', :path => './JainuneSecurityModule'";

function addSecurityPod(contents) {
  if (/^\s*pod ['"]JainuneSecurityModule['"]/m.test(contents)) return contents;
  const target = /^target\s+['"][^'"]+['"]\s+do\s*$/m;
  if (!target.test(contents)) throw new Error("Cannot locate the iOS application target in Podfile");
  // Insert a standalone statement; never split use_native_modules!(config_command).
  return contents.replace(target, (line) => `${line}\n${POD_LINE}`);
}

module.exports = { addSecurityPod };
