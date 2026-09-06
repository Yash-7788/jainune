/**
 * In-App Legal & Compliance Modal
 *
 * Displays full, hosted-equivalent legal documents, DPDP privacy terms,
 * community guidelines, and CSAE child-safety disclosures directly within the app.
 */

import React, { useState } from "react";
import {
  Modal,
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  SafeAreaView,
  Linking,
} from "react-native";
import { colors, spacing, radii, typography } from "../../theme/tokens";

export type LegalDocType = "privacy" | "terms" | "child_safety" | "community" | "deletion";

interface LegalModalProps {
  visible: boolean;
  initialDoc?: LegalDocType;
  onClose: () => void;
}

const DOC_TITLES: Record<LegalDocType, string> = {
  privacy: "Privacy Policy",
  terms: "Terms of Service",
  child_safety: "Child Safety (18+)",
  community: "Community Guidelines",
  deletion: "Data Erasure",
};

const DOC_URLS: Record<LegalDocType, string> = {
  privacy: "https://jainune.com/legal/privacy",
  terms: "https://jainune.com/legal/terms",
  child_safety: "https://jainune.com/legal/child-safety",
  community: "https://jainune.com/legal/community-guidelines",
  deletion: "https://jainune.com/legal/delete-account",
};

export default function LegalModal({
  visible,
  initialDoc = "privacy",
  onClose,
}: LegalModalProps) {
  const [activeTab, setActiveTab] = useState<LegalDocType>(initialDoc);

  // Sync tab when initialDoc changes on open
  React.useEffect(() => {
    if (visible) {
      setActiveTab(initialDoc);
    }
  }, [visible, initialDoc]);

  const handleOpenExternal = () => {
    Linking.openURL(DOC_URLS[activeTab]).catch(() => {});
  };

  return (
    <Modal visible={visible} animationType="slide" transparent={false} onRequestClose={onClose}>
      <SafeAreaView style={styles.safeArea}>
        {/* Header */}
        <View style={styles.header}>
          <Text style={styles.headerTitle}>{DOC_TITLES[activeTab]}</Text>
          <TouchableOpacity style={styles.closeBtn} onPress={onClose}>
            <Text style={styles.closeText}>✕</Text>
          </TouchableOpacity>
        </View>

        {/* Tab selector */}
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.tabBar}
        >
          {(Object.keys(DOC_TITLES) as LegalDocType[]).map((tab) => {
            const isActive = activeTab === tab;
            return (
              <TouchableOpacity
                key={tab}
                style={[styles.tab, isActive && styles.tabActive]}
                onPress={() => setActiveTab(tab)}
              >
                <Text style={[styles.tabText, isActive && styles.tabTextActive]}>
                  {DOC_TITLES[tab]}
                </Text>
              </TouchableOpacity>
            );
          })}
        </ScrollView>

        {/* Document Content */}
        <ScrollView style={styles.content} contentContainerStyle={styles.contentInner}>
          {activeTab === "privacy" && <PrivacyContent />}
          {activeTab === "terms" && <TermsContent />}
          {activeTab === "child_safety" && <ChildSafetyContent />}
          {activeTab === "community" && <CommunityContent />}
          {activeTab === "deletion" && <DeletionContent />}

          <TouchableOpacity style={styles.externalLinkBtn} onPress={handleOpenExternal}>
            <Text style={styles.externalLinkText}>Open Full Document on Web ↗</Text>
          </TouchableOpacity>
        </ScrollView>
      </SafeAreaView>
    </Modal>
  );
}

function PrivacyContent() {
  return (
    <View>
      <Text style={styles.effectiveDate}>Effective Date: September 2026 · Jainune Technologies Inc.</Text>
      <Text style={styles.sectionHeader}>1. Notice & Consent Under DPDP Act 2023</Text>
      <Text style={styles.paragraph}>
        Jainune collects and processes personal information strictly to deliver cultural matchmaking services.
        By using the app, you provide explicit consent to process your specified data attributes.
      </Text>
      <Text style={styles.sectionHeader}>2. Categories of Information Collected</Text>
      <Text style={styles.bullet}>• Basic Profile: Name, age, verified phone/email, gender, and photographs.</Text>
      <Text style={styles.bullet}>• Cultural Attributes: Jain sect, dietary strictness (onion/garlic, root vegetables), and Paryushan observances.</Text>
      <Text style={styles.bullet}>• Approximate Location: Used only for regional matching (Mumbai MMR, Pune, Bengaluru, Pan-India).</Text>
      <Text style={styles.bullet}>• Verification Media: Liveness selfie used exclusively for automated verification and immediately purged.</Text>
      <Text style={styles.sectionHeader}>3. Data Protection & Non-Sale</Text>
      <Text style={styles.paragraph}>
        We never sell or monetize your personal data. Data is encrypted in transit (TLS 1.3) and at rest (AES-256).
      </Text>
      <Text style={styles.sectionHeader}>4. Grievance Officer</Text>
      <Text style={styles.paragraph}>Contact: privacy@jainune.com · Response SLA: 48 business hours.</Text>
    </View>
  );
}

function TermsContent() {
  return (
    <View>
      <Text style={styles.effectiveDate}>Effective Date: September 2026</Text>
      <Text style={styles.sectionHeader}>1. Eligibility & Age Restriction</Text>
      <Text style={styles.paragraph}>
        You must be at least 18 years old to create an account or use Jainune. Any account found to be operated
        by an individual under 18 years of age will be immediately and permanently terminated.
      </Text>
      <Text style={styles.sectionHeader}>2. Acceptable Use & Ahimsa</Text>
      <Text style={styles.paragraph}>
        Jainune requires non-violent, truthful, and dignified communication. Harassment, deceptive behavior,
        commercial solicitation, and abusive messaging are strictly prohibited.
      </Text>
      <Text style={styles.sectionHeader}>3. Subscriptions & Digital Content</Text>
      <Text style={styles.paragraph}>
        Subscriptions (Jainune+) and consumable arcade tokens are managed via compliant platform billing.
        Renewals can be cancelled anytime before the next billing cycle.
      </Text>
      <Text style={styles.sectionHeader}>4. Zero Tolerance for Objectionable Content & EULA (Apple Guideline 1.2)</Text>
      <Text style={styles.paragraph}>
        Jainune enforces an absolute zero-tolerance policy against objectionable content and abusive users.
        Users agree not to post, transmit, or share any harassing, defamatory, abusive, sexually explicit,
        or hateful material. Any user who violates this policy will have their content removed and their account
        permanently banned within 24 hours of reporting.
      </Text>
    </View>
  );
}

function ChildSafetyContent() {
  return (
    <View>
      <View style={styles.alertBox}>
        <Text style={styles.alertTitle}>ZERO TOLERANCE FOR MINORS & CSAE</Text>
        <Text style={styles.alertBody}>
          Jainune strictly operates as an 18+ adult platform. We maintain an uncompromising, zero-tolerance policy
          towards Child Sexual Abuse Material (CSAM) and Child Sexual Exploitation and Abuse (CSAE).
        </Text>
      </View>
      <Text style={styles.sectionHeader}>1. Automated & Human Prevention</Text>
      <Text style={styles.paragraph}>
        All media uploads undergo automated perceptual hash screening against known CSAM databases prior to publishing.
        Any detected content is blocked instantly.
      </Text>
      <Text style={styles.sectionHeader}>2. Mandatory Law Enforcement Reporting</Text>
      <Text style={styles.paragraph}>
        In accordance with legal requirements, all violations are reported immediately to the National Center for
        Missing & Exploited Children (NCMEC) and relevant Indian cyber law enforcement authorities.
      </Text>
      <Text style={styles.sectionHeader}>3. Urgent Reporting Contact</Text>
      <Text style={styles.paragraph}>
        Dedicated Child Safety Officer: safety@jainune.com{"\n"}
        Emergency Response SLA: Under 1 hour.
      </Text>
    </View>
  );
}

function CommunityContent() {
  return (
    <View>
      <Text style={styles.effectiveDate}>Our Core Principles</Text>
      <Text style={styles.sectionHeader}>1. Mutual Dignity & Respect</Text>
      <Text style={styles.paragraph}>
        Every member is here to build meaningful connections. Be respectful of boundaries and cultural differences.
      </Text>
      <Text style={styles.sectionHeader}>2. Authentic Identity</Text>
      <Text style={styles.paragraph}>
        Use real photographs and accurate profile information. Impersonation or misleading representations
        are grounds for immediate removal.
      </Text>
      <Text style={styles.sectionHeader}>3. Reporting & Safety Tools</Text>
      <Text style={styles.paragraph}>
        You can block or report any profile or message instantly using the 3-dot menu on any screen.
      </Text>
    </View>
  );
}

function DeletionContent() {
  return (
    <View>
      <Text style={styles.sectionHeader}>Right to Erasure (DPDP Act & App Store Guidelines)</Text>
      <Text style={styles.paragraph}>
        You have complete ownership of your personal data. You can delete your account at any time:
      </Text>
      <Text style={styles.bullet}>• In-App: Settings &rarr; Account &rarr; Delete Account</Text>
      <Text style={styles.bullet}>• Web Portal: https://jainune.com/legal/delete-account</Text>
      <Text style={styles.bullet}>• Email Request: support@jainune.com</Text>
      <Text style={styles.sectionHeader}>Data Removal Timeline</Text>
      <Text style={styles.paragraph}>
        Your profile, pictures, chat messages, and search indexes are permanently erased within 72 hours of confirmation.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: colors.obsidian || "#0D0F14",
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: spacing.base,
    paddingVertical: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.border || "#232733",
  },
  headerTitle: {
    ...typography.headline,
    color: colors.gold || "#D4AF37",
    fontSize: 18,
    fontWeight: "700",
  },
  closeBtn: {
    padding: spacing.xs,
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: "#1A1E29",
    alignItems: "center",
    justifyContent: "center",
  },
  closeText: {
    color: colors.sand || "#C5C9D3",
    fontSize: 16,
    fontWeight: "700",
  },
  tabBar: {
    flexDirection: "row",
    paddingHorizontal: spacing.base,
    paddingVertical: spacing.sm,
    gap: spacing.xs,
  },
  tab: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: radii.full || 20,
    backgroundColor: "#161A23",
    borderWidth: 1,
    borderColor: colors.border || "#232733",
  },
  tabActive: {
    backgroundColor: colors.saffron || "#FF9933",
    borderColor: colors.saffron || "#FF9933",
  },
  tabText: {
    ...typography.bodySmall,
    color: colors.sand || "#C5C9D3",
    fontSize: 13,
  },
  tabTextActive: {
    color: colors.obsidian || "#0D0F14",
    fontWeight: "700",
  },
  content: {
    flex: 1,
  },
  contentInner: {
    padding: spacing.base,
    paddingBottom: spacing.xxl,
  },
  effectiveDate: {
    ...typography.caption,
    color: colors.mid || "#8C94A6",
    marginBottom: spacing.md,
  },
  sectionHeader: {
    ...typography.headline,
    color: colors.gold || "#D4AF37",
    fontSize: 16,
    marginTop: spacing.md,
    marginBottom: spacing.xs,
    fontWeight: "600",
  },
  paragraph: {
    ...typography.body,
    color: colors.sand || "#C5C9D3",
    lineHeight: 22,
    marginBottom: spacing.sm,
    fontSize: 14,
  },
  bullet: {
    ...typography.body,
    color: colors.sand || "#C5C9D3",
    lineHeight: 22,
    paddingLeft: spacing.xs,
    marginBottom: spacing.xs,
    fontSize: 14,
  },
  alertBox: {
    backgroundColor: "rgba(229, 57, 53, 0.12)",
    borderWidth: 1,
    borderColor: "#E53935",
    borderRadius: radii.md || 8,
    padding: spacing.md,
    marginBottom: spacing.md,
  },
  alertTitle: {
    color: "#FF5252",
    fontWeight: "700",
    fontSize: 13,
    marginBottom: spacing.xs,
    letterSpacing: 0.5,
  },
  alertBody: {
    color: "#FFCDD2",
    fontSize: 13,
    lineHeight: 19,
  },
  externalLinkBtn: {
    marginTop: spacing.xl,
    paddingVertical: spacing.md,
    borderRadius: radii.md || 8,
    backgroundColor: "#161A23",
    borderWidth: 1,
    borderColor: colors.saffron || "#FF9933",
    alignItems: "center",
  },
  externalLinkText: {
    color: colors.saffron || "#FF9933",
    fontWeight: "600",
    fontSize: 14,
  },
});
