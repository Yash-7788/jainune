"""
Legal, Compliance, and Child Safety Router

Fulfills:
- Google Play Developer Policy (Child Safety Standards, CSAE Zero Tolerance)
- Google Play User Data Policy (Public Privacy Policy & External Account Deletion)
- Digital Personal Data Protection Act (DPDP) 2023
- Apple App Store Guideline 5.1 (Data Privacy & Legal)
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["Legal"])

_BASE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} - Jainune</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0D0F14; color: #E8EBF2; line-height: 1.6; max-width: 800px; margin: 0 auto; padding: 2rem 1.5rem; }}
    h1 {{ color: #FF9933; border-bottom: 1px solid #232733; padding-bottom: 0.5rem; }}
    h2 {{ color: #D4AF37; margin-top: 1.8rem; }}
    a {{ color: #FF9933; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .badge {{ display: inline-block; background: #1C202B; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 0.85rem; color: #8C94A6; margin-bottom: 1.5rem; }}
    .card {{ background: #141822; border: 1px solid #232733; border-radius: 8px; padding: 1.25rem; margin: 1rem 0; }}
    ul {{ padding-left: 1.2rem; }}
    li {{ margin-bottom: 0.5rem; }}
    footer {{ margin-top: 3rem; border-top: 1px solid #232733; padding-top: 1rem; font-size: 0.85rem; color: #6C7280; text-align: center; }}
  </style>
</head>
<body>
  <h1>{title}</h1>
  <div class="badge">Effective Date: September 2026 · Jainune Technologies Inc.</div>
  {content}
  <footer>
    &copy; 2026 Jainune. All rights reserved. &nbsp;|&nbsp;
    <a href="/legal/privacy">Privacy</a> &nbsp;|&nbsp;
    <a href="/legal/terms">Terms</a> &nbsp;|&nbsp;
    <a href="/legal/child-safety">Child Safety</a> &nbsp;|&nbsp;
    <a href="/legal/delete-account">Delete Account</a>
  </footer>
</body>
</html>
"""

@router.get("/privacy", response_class=HTMLResponse)
@router.get("/legal/privacy", response_class=HTMLResponse)
async def privacy_policy():
    content = """
    <h2>1. Introduction</h2>
    <p>Jainune ("we", "our", "us") values your privacy. This policy outlines how we collect, handle, and protect your personal data in accordance with the Digital Personal Data Protection Act (DPDP) 2023 and global privacy frameworks.</p>

    <h2>2. Data We Collect</h2>
    <ul>
      <li><strong>Identity Data:</strong> Name, phone number, email address, date of birth, gender, and photograph.</li>
      <li><strong>Community & Dietary Profile:</strong> Jain sect, dietary strictness (e.g. root vegetables, onion-garlic preferences), and Paryushan observances (provided voluntarily with consent).</li>
      <li><strong>Verification Data:</strong> Selfie capture strictly for algorithmic liveness and photo verification, permanently purged after verification.</li>
      <li><strong>Approximate Location:</strong> City and neighborhood-level approximate location (with explicit permission) to suggest compatible connections.</li>
    </ul>

    <h2>3. Data Usage & Purpose Limitation</h2>
    <p>We process your data strictly to facilitate authentic matchmaking, verify account authenticity, and prevent abuse. We do not sell your personal data to third parties or advertisers.</p>

    <h2>4. Right to Erasure & Account Deletion</h2>
    <p>You have the absolute right to delete your account and all associated data at any time via the in-app Settings menu or through our <a href="/legal/delete-account">External Account Deletion Portal</a>.</p>

    <h2>5. Grievance Redressal</h2>
    <p>For data privacy queries or grievance reports: <strong>privacy@jainune.com</strong>.</p>
    """
    return _BASE_HTML.format(title="Privacy Policy", content=content)


@router.get("/terms", response_class=HTMLResponse)
@router.get("/legal/terms", response_class=HTMLResponse)
async def terms_of_service():
    content = """
    <h2>1. Eligibility</h2>
    <p>You must be at least 18 years of age to register or use Jainune. By using the service, you represent and warrant that you have the legal capacity to enter into this agreement.</p>

    <h2>2. Community Conduct</h2>
    <p>Jainune is built on ahimsa (non-violence), truth, and mutual respect. Users agree not to harass, impersonate, defraud, or transmit abusive or sexually explicit content.</p>

    <h2>3. Subscriptions & In-App Purchases</h2>
    <p>Jainune+ subscriptions and Serendipity Arcade tokens are subject to platform billing guidelines (Google Play / App Store / authorized payment gateways). Subscriptions auto-renew unless cancelled at least 24 hours prior to the end of the billing period.</p>

    <h2>4. Account Termination</h2>
    <p>We reserve the right to suspend or terminate accounts that violate our terms, guidelines, or safety policies.</p>
    """
    return _BASE_HTML.format(title="Terms of Service", content=content)


@router.get("/child-safety", response_class=HTMLResponse)
@router.get("/legal/child-safety", response_class=HTMLResponse)
async def child_safety_standards():
    content = """
    <div class="card" style="border-color: #E53935; background: rgba(229,57,53,0.08);">
      <h3 style="color: #FF5252; margin-top: 0;">Zero-Tolerance Policy on Child Sexual Abuse and Exploitation (CSAE)</h3>
      <p>Jainune is strictly an 18+ adult matchmaking service. We maintain a zero-tolerance policy against Child Sexual Abuse Material (CSAM), Child Sexual Exploitation and Abuse (CSAE), and any form of child grooming, solicitation, or harm.</p>
    </div>

    <h2>1. Strict Age Gate Enforcement</h2>
    <p>Users must authenticate that they are 18 years of age or older. Accounts discovered or suspected of being underage are immediately banned and permanently purged.</p>

    <h2>2. Automated & Human Moderation</h2>
    <p>All uploaded photos and media are analyzed prior to publication for policy compliance, including automated perceptual hash detection against known CSAM databases. Violative content is blocked instantly.</p>

    <h2>3. Mandatory Legal Reporting</h2>
    <p>In compliance with international and national laws, Jainune immediately reports any identified child exploitation material or grooming attempts to the <strong>National Center for Missing & Exploited Children (NCMEC)</strong> and Indian law enforcement authorities.</p>

    <h2>4. Child Safety Contact & Urgent Reporting</h2>
    <p>If you encounter content or conduct involving minors on our platform, report it immediately in-app or via our 24/7 dedicated safety response contact:</p>
    <p><strong>Designated Child Safety Officer:</strong> <a href="mailto:safety@jainune.com">safety@jainune.com</a><br>
    Response SLA: Under 1 hour for child safety and emergency escalations.</p>
    """
    return _BASE_HTML.format(title="Child Safety & CSAE Prevention Standards", content=content)


@router.get("/community-guidelines", response_class=HTMLResponse)
@router.get("/legal/community-guidelines", response_class=HTMLResponse)
async def community_guidelines():
    content = """
    <h2>Our Core Values</h2>
    <p>Jainune brings modern singles together grounded in shared cultural values, transparency, and dignity.</p>
    <ul>
      <li><strong>Ahimsa in Communication:</strong> Treat every match with courtesy and empathy. Harassment, hateful speech, and intimidation will result in immediate bans.</li>
      <li><strong>Honesty & Authenticity:</strong> Use real photos and truthful information. Catfishing and impersonation are strictly forbidden.</li>
      <li><strong>Consent & Privacy:</strong> Do not capture, record, or distribute another member's media or private messages without explicit consent.</li>
    </ul>
    """
    return _BASE_HTML.format(title="Community Guidelines", content=content)


@router.get("/delete-account", response_class=HTMLResponse)
@router.get("/legal/delete-account", response_class=HTMLResponse)
async def delete_account_portal():
    content = """
    <p>In accordance with Google Play User Data policies and DPDP Right to Erasure, Jainune provides both in-app and external web-based account deletion.</p>

    <div class="card">
      <h3>Method 1: In-App Instant Deletion (Recommended)</h3>
      <p>Open the Jainune app &rarr; Settings &rarr; Account &rarr; Delete Account. This instantly revokes all tokens, erases personal identifiers, and wipes all media and matches.</p>
    </div>

    <div class="card">
      <h3>Method 2: External Web Deletion Request</h3>
      <p>If you no longer have access to the Jainune app on your device, you may submit an erasure request directly via email:</p>
      <p>Send an email from your registered email address or phone number to: <strong>support@jainune.com</strong> with the subject <em>"Account Deletion Request"</em>.</p>
      <p><strong>What gets deleted:</strong> Profile information, photographs, voice notes, chat history, and biometric liveness metadata are permanently removed within 48 hours of verification.</p>
    </div>
    """
    return _BASE_HTML.format(title="Account Deletion & Data Erasure Portal", content=content)
