require "json"

package = JSON.parse(File.read(File.join(__dir__, "../../package.json")))

Pod::Spec.new do |s|
  s.name         = "JainuneSecurityModule"
  s.version      = package["version"] || "1.0.0"
  s.summary      = "Jainune iOS Security Module"
  s.homepage     = "https://jainune.com"
  s.license      = "Proprietary"
  s.authors      = { "Jainune" => "security@jainune.com" }
  s.platforms    = { :ios => "13.4" }
  s.source       = { :git => "" }
  s.source_files = "*.{h,m}"
  s.dependency "React-Core"
end
