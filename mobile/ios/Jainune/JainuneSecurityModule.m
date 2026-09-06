#import "JainuneSecurityModule.h"
#import <UIKit/UIKit.h>
#import <sys/sysctl.h>
#import <mach-o/dyld.h>

@implementation JainuneSecurityModule {
  BOOL _hasListeners;
  UIView *_blankingView;
}

RCT_EXPORT_MODULE();

+ (BOOL)requiresMainQueueSetup {
  return YES;
}

- (NSArray<NSString *> *)supportedEvents {
  return @[@"ScreenRecordingStateChanged"];
}

- (void)startObserving {
  _hasListeners = YES;
  [[NSNotificationCenter defaultCenter] addObserver:self
                                           selector:@selector(handleScreenCaptureChange:)
                                               name:UIScreenCapturedDidChangeNotification
                                             object:nil];
}

- (void)stopObserving {
  _hasListeners = NO;
  [[NSNotificationCenter defaultCenter] removeObserver:self
                                                  name:UIScreenCapturedDidChangeNotification
                                                object:nil];
}

- (void)handleScreenCaptureChange:(NSNotification *)notification {
  BOOL isCaptured = [UIScreen mainScreen].isCaptured;
  dispatch_async(dispatch_get_main_queue(), ^{
    [self updateBlankingView:isCaptured];
  });
  if (_hasListeners) {
    [self sendEventWithName:@"ScreenRecordingStateChanged" body:@{@"isCaptured": @(isCaptured)}];
  }
}

- (void)updateBlankingView:(BOOL)isCaptured {
  UIWindow *keyWindow = [UIApplication sharedApplication].keyWindow;
  if (!keyWindow) return;

  if (isCaptured) {
    if (!_blankingView) {
      _blankingView = [[UIView alloc] initWithFrame:keyWindow.bounds];
      _blankingView.backgroundColor = [UIColor colorWithRed:0.05 green:0.06 blue:0.08 alpha:1.0];
      UILabel *label = [[UILabel alloc] initWithFrame:_blankingView.bounds];
      label.text = @"Screen recording is disabled for privacy.";
      label.textColor = [UIColor whiteColor];
      label.textAlignment = NSTextAlignmentCenter;
      label.font = [UIFont systemFontOfSize:16 weight:UIFontWeightBold];
      [_blankingView addSubview:label];
    }
    [keyWindow addSubview:_blankingView];
    [keyWindow bringSubviewToFront:_blankingView];
  } else {
    [_blankingView removeFromSuperview];
    _blankingView = nil;
  }
}

RCT_EXPORT_METHOD(enableScreenRecordingProtection) {
  dispatch_async(dispatch_get_main_queue(), ^{
    [self updateBlankingView:[UIScreen mainScreen].isCaptured];
  });
}

RCT_EXPORT_METHOD(isDeviceRooted:(RCTPromiseResolveBlock)resolve rejecter:(RCTPromiseRejectBlock)reject) {
  // Check jailbreak indicators
  NSArray *jailbreakPaths = @[
    @"/Applications/Cydia.app",
    @"/Library/MobileSubstrate/MobileSubstrate.dylib",
    @"/bin/bash",
    @"/usr/sbin/sshd",
    @"/etc/apt",
    @"/private/var/lib/apt/",
    @"/Applications/Sileo.app"
  ];
  for (NSString *path in jailbreakPaths) {
    if ([[NSFileManager defaultManager] fileExistsAtPath:path]) {
      resolve(@YES);
      return;
    }
  }
  // Check writing outside sandbox
  NSError *error;
  NSString *testPath = @"/private/jailbreak_test.txt";
  [@"test" writeToFile:testPath atomically:YES encoding:NSUTF8StringEncoding error:&error];
  if (!error) {
    [[NSFileManager defaultManager] removeItemAtPath:testPath error:nil];
    resolve(@YES);
    return;
  }
  resolve(@NO);
}

RCT_EXPORT_METHOD(isDebuggerAttached:(RCTPromiseResolveBlock)resolve rejecter:(RCTPromiseRejectBlock)reject) {
  int name[4];
  struct kinfo_proc info;
  size_t info_size = sizeof(info);
  info.kp_proc.p_flag = 0;

  name[0] = CTL_KERN;
  name[1] = KERN_PROC;
  name[2] = KERN_PROC_PID;
  name[3] = getpid();

  if (sysctl(name, 4, &info, &info_size, NULL, 0) == -1) {
    resolve(@NO);
    return;
  }
  BOOL isAttached = (info.kp_proc.p_flag & P_TRACED) != 0;
  resolve(@(isAttached));
}

RCT_EXPORT_METHOD(detectFrida:(RCTPromiseResolveBlock)resolve rejecter:(RCTPromiseRejectBlock)reject) {
  uint32_t count = _dyld_image_count();
  for (uint32_t i = 0; i < count; i++) {
    const char *name = _dyld_get_image_name(i);
    if (name && (strstr(name, "FridaGadget") || strstr(name, "frida") || strstr(name, "cynject"))) {
      resolve(@YES);
      return;
    }
  }
  resolve(@NO);
}

RCT_EXPORT_METHOD(emergencyPurgeStorage) {
  // Clear keychain items if needed
  NSDictionary *query = @{(__bridge id)kSecClass: (__bridge id)kSecClassGenericPassword};
  SecItemDelete((__bridge CFDictionaryRef)query);
}

RCT_EXPORT_METHOD(exitApp) {
  // Apple App Store Guideline 2.5.1 prohibits calling exit().
  // UI blanking preserves screen privacy while avoiding artificial crash.
  dispatch_async(dispatch_get_main_queue(), ^{
    [self updateBlankingView:YES];
  });
}

@end
