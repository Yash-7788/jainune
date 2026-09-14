/**
 * In-App Legal & Compliance Modal — Jainune
 *
 * Premium native design conforming strictly to Jainune Warm/Cream & Saffron design system.
 * Zero-distortion horizontal tabs, accessible high-contrast typography, and compliant
 * DPDP 2023, CSAE (18+), EULA, and Data Erasure disclosures.
 */

import React, { useState, useEffect } from "react";
import {
  Modal,
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  Linking,
  StatusBar,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { colors, spacing, radii, typography } from "../../theme/tokens";

export type LegalDocType = "privacy" | "terms" | "child_safety" | "community" | "deletion";

interface LegalModalProps {
  visible: boolean;
  initialDoc?: LegalDocType;
  onClose: () => void;
}

const DOC_TITLES: Record<LegalDocType, string> = {
  terms: "Terms of Service",
  privacy: "Privacy Policy",
  child_safety: "Safety & 18+",
  community: "Community Guidelines",
  deletion: "Data Erasure",
};

const DOC_URLS: Record<LegalDocType, string> = {
  terms: "https://jainune.com/legal/terms",
  privacy: "https://jainune.com/legal/privacy",
  child_safety: "https://jainune.com/legal/child-safety",
  community: "https://jainune.com/legal/community-guidelines",
  deletion: "https://jainune.com/legal/delete-account",
};

export default function LegalModal({
  visible,
  initialDoc = "terms",
  onClose,
}: LegalModalProps) {
  const [activeTab, setActiveTab] = useState<LegalDocType>(initialDoc);

  useEffect(() => {
    if (visible) {
      setActiveTab(initialDoc);
    }
  }, [visible, initialDoc]);

  const handleOpenExternal = () => {
    Linking.openURL(DOC_URLS[activeTab]).catch(() => {});
  };

  return (
    <Modal
      visible={visible}
      animationType="slide"
      presentationStyle="pageSheet"
      onRequestClose={onClose}
    >
      <SafeAreaView style={styles.safeArea}>
        <StatusBar barStyle="dark-content" backgroundColor={colors.bg} />

        {/* Top Navigation Bar */}
        <View style={styles.header}>
          <View style={styles.headerLeft}>
            <Text style={styles.headerPretitle}>LEGAL & COMPLIANCE</Text>
            <Text style={styles.headerTitle} numberOfLines={1}>
              {DOC_TITLES[activeTab]}
            </Text>
          </View>
          <TouchableOpacity
            style={styles.closeBtn}
            onPress={onClose}
            hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}
            activeOpacity={0.7}
          >
            <Text style={styles.closeIcon}>✕</Text>
          </TouchableOpacity>
        </View>

        {/* Horizontal Tab Chips */}
        <View style={styles.tabBarWrapper}>
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.tabBarContent}
          >
            {(Object.keys(DOC_TITLES) as LegalDocType[]).map((tab) => {
              const isActive = activeTab === tab;
              return (
                <TouchableOpacity
                  key={tab}
                  style={[styles.tab, isActive && styles.tabActive]}
                  onPress={() => setActiveTab(tab)}
                  activeOpacity={0.8}
                >
                  <Text style={[styles.tabText, isActive && styles.tabTextActive]}>
                    {DOC_TITLES[tab]}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </ScrollView>
        </View>

        {/* Scrollable Document Content */}
        <ScrollView
          style={styles.contentScroll}
          contentContainerStyle={styles.contentInner}
          showsVerticalScrollIndicator={true}
        >
          {activeTab === "terms" && <TermsContent />}
          {activeTab === "privacy" && <PrivacyContent />}
          {activeTab === "child_safety" && <ChildSafetyContent />}
          {activeTab === "community" && <CommunityContent />}
          {activeTab === "deletion" && <DeletionContent />}

          {/* Web Document Link */}
          <TouchableOpacity
            style={styles.externalLinkBtn}
            onPress={handleOpenExternal}
            activeOpacity={0.85}
          >
            <Text style={styles.externalLinkText}>Open Full Legal Document on Web ↗</Text>
          </TouchableOpacity>

          <Text style={styles.footerNotice}>
            Jainune Technologies Inc. · All Rights Reserved
          </Text>
        </ScrollView>
      </SafeAreaView>
    </Modal>
  );
}

function TermsContent() {
  return (
    <View>
      <View style={styles.badgeCard}>
        <Text style={styles.badgeText}>EFFECTIVE DATE: SEPTEMBER 2026</Text>
        <Text style={styles.cardLead}>
          Please read these Terms of Service carefully before creating your Jainune account.
        </Text>
      </View>

      <View style={styles.sectionCard}>
        <Text style={styles.sectionHeader}>1. Eligibility & Age Restriction</Text>
        <Text style={styles.paragraph}>
          You must be at least 18 years old to create an account or use Jainune. Any account found to be
          operated by an individual under 18 years of age will be immediately and permanently terminated.
        </Text>

        <Text style={styles.sectionHeader}>2. Acceptable Use & Ahimsa Standards</Text>
        <Text style={styles.paragraph}>
          Jainune requires non-violent, truthful, and dignified communication. Harassment, deceptive
          behavior, commercial solicitation, impersonation, and abusive messaging are strictly prohibited.
        </Text>

        <Text style={styles.sectionHeader}>3. Subscriptions & Billing Terms</Text>
        <Text style={styles.paragraph}>
          Premium memberships and micro-transactions (Serendipity Arcade, Boosts) are billed through the
          Google Play Store or Apple App Store. Subscriptions renew automatically unless cancelled at
          least 24 hours prior to the current billing period.
        </Text>

        <Text style={styles.sectionHeader}>4. Zero Tolerance for Objectionable Content & EULA</Text>
        <View style={styles.alertBox}>
          <Text style={styles.alertTitle}>MANDATORY APPLE & GOOGLE SAFETY CLAUSE</Text>
          <Text style={styles.alertBody}>
            Jainune enforces absolute zero-tolerance for objectionable content and abusive users.
            Harassing, sexually explicit, hateful, or abusive material results in immediate content removal
            and a permanent ban within 24 hours of reporting.
          </Text>
        </View>
      </View>
    </View>
  );
}

function PrivacyContent() {
  return (
    <View>
      <View style={styles.badgeCard}>
        <Text style={styles.badgeText}>DPDP ACT 2023 COMPLIANT</Text>
        <Text style={styles.cardLead}>
          Your privacy, dignity, and personal cultural choices are protected with bank-grade encryption.
        </Text>
      </View>

      <View style={styles.sectionCard}>
        <Text style={styles.sectionHeader}>1. Notice & Consent Under DPDP Act 2023</Text>
        <Text style={styles.paragraph}>
          Jainune collects and processes personal information strictly to deliver cultural matchmaking services.
          By using the app, you provide explicit, revocable consent to process specified profile attributes.
        </Text>

        <Text style={styles.sectionHeader}>2. Categories of Information Collected</Text>
        <View style={styles.bulletRow}>
          <View style={styles.bulletDot} />
          <Text style={styles.bulletText}>
            <Text style={styles.bulletBold}>Basic Profile: </Text>
            Name, age, verified phone/email, gender, and photographs.
          </Text>
        </View>
        <View style={styles.bulletRow}>
          <View style={styles.bulletDot} />
          <Text style={styles.bulletText}>
            <Text style={styles.bulletBold}>Cultural Attributes: </Text>
            Jain sect, dietary strictness (onion/garlic, root vegetables), and Paryushan observances.
          </Text>
        </View>
        <View style={styles.bulletRow}>
          <View style={styles.bulletDot} />
          <Text style={styles.bulletText}>
            <Text style={styles.bulletBold}>Location: </Text>
            City-level regional matching only (exact GPS coordinates are never exposed).
          </Text>
        </View>
        <View style={styles.bulletRow}>
          <View style={styles.bulletDot} />
          <Text style={styles.bulletText}>
            <Text style={styles.bulletBold}>Liveness Media: </Text>
            Verification selfie used solely for automated identity verification and immediately purged.
          </Text>
        </View>

        <Text style={styles.sectionHeader}>3. Data Protection & Non-Sale</Text>
        <Text style={styles.paragraph}>
          We never sell, rent, or monetize your personal data. All information is encrypted in transit
          (TLS 1.3) and at rest (AES-256).
        </Text>

        <Text style={styles.sectionHeader}>4. Grievance Officer Contact</Text>
        <View style={styles.contactCard}>
          <Text style={styles.contactEmail}>Email: privacy@jainune.com</Text>
          <Text style={styles.contactSub}>Response SLA: Within 48 business hours.</Text>
        </View>
      </View>
    </View>
  );
}

function ChildSafetyContent() {
  return (
    <View>
      <View style={styles.dangerAlertBox}>
        <Text style={styles.dangerAlertTitle}>ZERO TOLERANCE FOR MINORS & CSAE</Text>
        <Text style={styles.dangerAlertBody}>
          Jainune strictly operates as an 18+ adult matchmaking platform. We maintain an uncompromising,
          zero-tolerance policy towards Child Sexual Abuse Material (CSAM) and Child Sexual Exploitation
          and Abuse (CSAE).
        </Text>
      </View>

      <View style={styles.sectionCard}>
        <Text style={styles.sectionHeader}>1. Automated & Human Screening</Text>
        <Text style={styles.paragraph}>
          All media uploads undergo automated perceptual hash screening against known CSAM databases
          prior to publishing. Any detected content is blocked instantly.
        </Text>

        <Text style={styles.sectionHeader}>2. Mandatory Law Enforcement Escalation</Text>
        <Text style={styles.paragraph}>
          In accordance with global legal requirements, violations are reported immediately to the
          National Center for Missing & Exploited Children (NCMEC) and relevant cyber crime authorities.
        </Text>

        <Text style={styles.sectionHeader}>3. Emergency Contact</Text>
        <View style={styles.contactCard}>
          <Text style={styles.contactEmail}>Child Safety Officer: safety@jainune.com</Text>
          <Text style={styles.contactSub}>Emergency Response SLA: Under 1 hour.</Text>
        </View>
      </View>
    </View>
  );
}

function CommunityContent() {
  return (
    <View>
      <View style={styles.badgeCard}>
        <Text style={styles.badgeText}>AHIMSA & SATYA PRINCIPLES</Text>
        <Text style={styles.cardLead}>
          Building lifelong, culturally harmonious bonds rooted in respect and authenticity.
        </Text>
      </View>

      <View style={styles.sectionCard}>
        <Text style={styles.sectionHeader}>1. Mutual Dignity & Respect</Text>
        <Text style={styles.paragraph}>
          Every member is here to discover meaningful partnerships. Treat every match with courtesy,
          respect personal boundaries, and honor cultural choices.
        </Text>

        <Text style={styles.sectionHeader}>2. Authentic Identity</Text>
        <Text style={styles.paragraph}>
          Use current, real photographs and truthful profile details. Deceptive representations, catfishing,
          or commercial marketing result in permanent expulsion.
        </Text>

        <Text style={styles.sectionHeader}>3. Instant Safety Controls</Text>
        <Text style={styles.paragraph}>
          You can block or report any profile or conversation immediately using the three-dot menu on any
          screen. Blocked profiles cannot see or contact you ever again.
        </Text>
      </View>
    </View>
  );
}

function DeletionContent() {
  return (
    <View>
      <View style={styles.badgeCard}>
        <Text style={styles.badgeText}>RIGHT TO ERASURE</Text>
        <Text style={styles.cardLead}>
          You retain complete autonomy over your data under the DPDP Act 2023 and App Store Guidelines.
        </Text>
      </View>

      <View style={styles.sectionCard}>
        <Text style={styles.sectionHeader}>How to Permanently Delete Your Account</Text>
        <View style={styles.bulletRow}>
          <View style={styles.bulletDot} />
          <Text style={styles.bulletText}>
            <Text style={styles.bulletBold}>In-App: </Text>
            Go to Settings → Account → Delete Account
          </Text>
        </View>
        <View style={styles.bulletRow}>
          <View style={styles.bulletDot} />
          <Text style={styles.bulletText}>
            <Text style={styles.bulletBold}>Web Portal: </Text>
            https://jainune.com/legal/delete-account
          </Text>
        </View>
        <View style={styles.bulletRow}>
          <View style={styles.bulletDot} />
          <Text style={styles.bulletText}>
            <Text style={styles.bulletBold}>Direct Email: </Text>
            support@jainune.com
          </Text>
        </View>

        <Text style={styles.sectionHeader}>Data Erasure Timeline</Text>
        <Text style={styles.paragraph}>
          Upon confirmation, your profile, photos, chat messages, and search vectors are permanently
          purged across all database replicas and Redis caches within 72 hours.
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: colors.bg,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: spacing.base,
    paddingTop: spacing.sm,
    paddingBottom: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
    backgroundColor: colors.bg,
  },
  headerLeft: {
    flex: 1,
    paddingRight: spacing.md,
  },
  headerPretitle: {
    fontFamily: "Outfit_700Bold",
    fontSize: 11,
    color: colors.saffron,
    letterSpacing: 1.2,
    marginBottom: 2,
  },
  headerTitle: {
    fontFamily: "Outfit_800ExtraBold",
    fontSize: 22,
    color: colors.dark,
    lineHeight: 28,
  },
  closeBtn: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: colors.light,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: colors.border,
  },
  closeIcon: {
    fontFamily: "Outfit_700Bold",
    fontSize: 16,
    color: colors.dark,
  },
  tabBarWrapper: {
    height: 52,
    backgroundColor: colors.bg,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  tabBarContent: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: spacing.base,
    gap: spacing.xs,
  },
  tab: {
    height: 36,
    paddingHorizontal: spacing.md,
    borderRadius: radii.full,
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: "center",
    justifyContent: "center",
  },
  tabActive: {
    backgroundColor: colors.saffron,
    borderColor: colors.saffron,
    shadowColor: colors.saffron,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.25,
    shadowRadius: 4,
    elevation: 2,
  },
  tabText: {
    fontFamily: "Inter_500Medium",
    fontSize: 13,
    color: colors.mid,
  },
  tabTextActive: {
    fontFamily: "Outfit_700Bold",
    color: colors.white,
  },
  contentScroll: {
    flex: 1,
  },
  contentInner: {
    paddingHorizontal: spacing.base,
    paddingTop: spacing.base,
    paddingBottom: 48,
  },
  badgeCard: {
    backgroundColor: colors.saffronLight,
    borderRadius: radii.lg,
    padding: spacing.base,
    marginBottom: spacing.base,
    borderWidth: 1,
    borderColor: "#FFE0C2",
  },
  badgeText: {
    fontFamily: "Outfit_700Bold",
    fontSize: 11,
    color: colors.saffron,
    letterSpacing: 1,
    marginBottom: 4,
  },
  cardLead: {
    fontFamily: "Outfit_600SemiBold",
    fontSize: 14,
    color: colors.dark,
    lineHeight: 20,
  },
  sectionCard: {
    backgroundColor: colors.white,
    borderRadius: radii.xl,
    padding: spacing.base,
    borderWidth: 1,
    borderColor: colors.border,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04,
    shadowRadius: 3,
    elevation: 1,
    marginBottom: spacing.base,
  },
  sectionHeader: {
    fontFamily: "Outfit_700Bold",
    fontSize: 16,
    color: colors.dark,
    marginTop: spacing.md,
    marginBottom: spacing.xs,
  },
  paragraph: {
    fontFamily: "Inter_400Regular",
    fontSize: 14,
    color: "#3C3C43",
    lineHeight: 22,
    marginBottom: spacing.sm,
  },
  bulletRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    marginBottom: spacing.xs,
    gap: spacing.xs,
  },
  bulletDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: colors.saffron,
    marginTop: 8,
    flexShrink: 0,
  },
  bulletText: {
    fontFamily: "Inter_400Regular",
    fontSize: 13.5,
    lineHeight: 21,
    color: "#3C3C43",
    flex: 1,
  },
  bulletBold: {
    fontFamily: "Outfit_600SemiBold",
    color: colors.dark,
  },
  alertBox: {
    backgroundColor: colors.saffronLight,
    borderLeftWidth: 3,
    borderLeftColor: colors.saffron,
    padding: spacing.sm,
    borderRadius: radii.sm,
    marginTop: spacing.sm,
    marginBottom: spacing.sm,
  },
  alertTitle: {
    fontFamily: "Outfit_700Bold",
    fontSize: 12,
    color: colors.saffron,
    letterSpacing: 0.5,
    marginBottom: 4,
  },
  alertBody: {
    fontFamily: "Inter_400Regular",
    fontSize: 13,
    lineHeight: 19,
    color: colors.dark,
  },
  dangerAlertBox: {
    backgroundColor: colors.redLight,
    borderRadius: radii.lg,
    padding: spacing.base,
    borderWidth: 1,
    borderColor: "#FFCCD0",
    marginBottom: spacing.base,
  },
  dangerAlertTitle: {
    fontFamily: "Outfit_700Bold",
    fontSize: 12,
    color: colors.red,
    letterSpacing: 1,
    marginBottom: 4,
  },
  dangerAlertBody: {
    fontFamily: "Inter_400Regular",
    fontSize: 13.5,
    lineHeight: 20,
    color: "#7A1C1C",
  },
  contactCard: {
    backgroundColor: colors.light,
    borderRadius: radii.md,
    padding: spacing.sm,
    marginTop: spacing.xs,
    marginBottom: spacing.sm,
  },
  contactEmail: {
    fontFamily: "Outfit_600SemiBold",
    fontSize: 13.5,
    color: colors.dark,
  },
  contactSub: {
    fontFamily: "Inter_400Regular",
    fontSize: 12,
    color: colors.mid,
    marginTop: 2,
  },
  externalLinkBtn: {
    height: 48,
    borderRadius: radii.full,
    borderWidth: 1.5,
    borderColor: colors.saffron,
    backgroundColor: colors.saffronLight,
    alignItems: "center",
    justifyContent: "center",
    marginTop: spacing.sm,
    marginBottom: spacing.md,
  },
  externalLinkText: {
    fontFamily: "Outfit_700Bold",
    fontSize: 14,
    color: colors.saffron,
  },
  footerNotice: {
    fontFamily: "Inter_400Regular",
    fontSize: 11,
    color: colors.muted,
    textAlign: "center",
    marginTop: spacing.xs,
  },
});
