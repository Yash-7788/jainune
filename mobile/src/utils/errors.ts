/**
 * Error Dictionary — frontend_integration_contracts.md §6
 * Zero technical jargon or HTTP codes shown to user ever.
 */

export type ErrorCode =
  | "SESSION_EXPIRED"
  | "DISPOSABLE_EMAIL_BLOCKED"
  | "CLIENT_INTEGRITY_FAILED"
  | "OTP_RATE_LIMIT"
  | "INVALID_OTP"
  | "ACCOUNT_DELETED"
  | "ACCOUNT_SUSPENDED"
  | "ACCOUNT_BANNED"
  | "DAILY_LIMIT_REACHED"
  | "INSUFFICIENT_CREDITS"
  | "CONNECTION_PROBLEM"
  | "TIMEOUT"
  | "FEED_EMPTY"
  | "CHAT_NOT_ALLOWED"
  | "SMS_GATEWAY_BUSY"
  | "TEMPORARY_ERROR";

interface FriendlyError {
  title: string;
  message: string;
}

const ERROR_MAP: Record<ErrorCode, FriendlyError> = {
  SESSION_EXPIRED: {
    title: "Time Flies When Having Fun!",
    message:
      "Your session took a little beauty sleep. Please sign in again so you don't miss any new smiles!",
  },
  DISPOSABLE_EMAIL_BLOCKED: {
    title: "Real Connections Only!",
    message:
      "We love authentic vibes! Please use your personal or work email—burner inboxes break Cupid's heart.",
  },
  CLIENT_INTEGRITY_FAILED: {
    title: "Are You a Robot?",
    message:
      "Beep boop! Our anti-bot radar went off. Please make sure you're using the official Jainune mobile app.",
  },
  OTP_RATE_LIMIT: {
    title: "Patience, Young Cupid!",
    message:
      "Too many codes requested in a flash. Grab a sip of water and try again in a couple of minutes.",
  },
  INVALID_OTP: {
    title: "Vanished Like the Last Samosa!",
    message:
      "That 6-digit code doesn't match or has expired. Request a fresh code and we'll send it right over!",
  },
  ACCOUNT_DELETED: {
    title: "New Chapters Await",
    message:
      "This account has completed its journey and is no longer active. Create a fresh profile to start anew!",
  },
  ACCOUNT_SUSPENDED: {
    title: "Taking a Little Timeout",
    message: "Your account is taking a temporary pause. Reach out to our friendly support team for help.",
  },
  ACCOUNT_BANNED: {
    title: "Good Vibes Only",
    message: "This account has been closed to protect our community's trust and respect.",
  },
  DAILY_LIMIT_REACHED: {
    title: "Cupid's Quiver is Empty for Today!",
    message:
      "You've shared so much love today! You've used all your daily complimentary connects. Recharge with Gold or check back tomorrow!",
  },
  INSUFFICIENT_CREDITS: {
    title: "Out of Super Sparks!",
    message:
      "You need a Super Connect credit to send this note directly. Top up your coin wallet in the Arcade!",
  },
  CONNECTION_PROBLEM: {
    title: "Lost in the Cloud Clouds?",
    message:
      "Even true love needs strong Wi-Fi! We're having trouble catching your signal. Check your connection and retry.",
  },
  TIMEOUT: {
    title: "Lost in the Cloud Clouds?",
    message:
      "Even true love needs strong Wi-Fi! We're having trouble catching your signal. Check your connection and retry.",
  },
  FEED_EMPTY: {
    title: "You're All Caught Up!",
    message:
      "We've shown you all compatible profiles nearby. Expand your distance preference or check back later!",
  },
  CHAT_NOT_ALLOWED: {
    title: "Silence is Golden",
    message: "This conversation is taking a pause or is no longer active.",
  },
  SMS_GATEWAY_BUSY: {
    title: "The Carrier Pigeon is Resting",
    message:
      "Our SMS carrier is catching its breath! Give it 60 seconds and request your code again.",
  },
  TEMPORARY_ERROR: {
    title: "Our Servers Need a Chai Break",
    message:
      "Our servers got a bit starry-eyed and tripped over a wire! Our engineers are untangling it right now. Hang tight!",
  },
};

export function getFriendlyError(code: ErrorCode | string): FriendlyError {
  return ERROR_MAP[code as ErrorCode] ?? ERROR_MAP.TEMPORARY_ERROR;
}
