/**
 * Branding configuration — white-label friendly.
 * 
 * Clients customize the top section (org name, logo, tagline).
 * CognitionShift appears as the platform provider, subtle and secondary.
 * 
 * To customize for a deployment:
 *   1. Set NEXT_PUBLIC_ORG_NAME, NEXT_PUBLIC_ORG_LOGO_URL, etc.
 *   2. Or edit the defaults below.
 */

export const branding = {
  // === Client branding (prominent) ===
  orgName: process.env.NEXT_PUBLIC_ORG_NAME || "",
  orgLogoUrl: process.env.NEXT_PUBLIC_ORG_LOGO_URL || "",
  orgTagline: process.env.NEXT_PUBLIC_ORG_TAGLINE || "",

  // === Platform branding (subtle) ===
  platformName: "CognitionShift",
  productName: "Enterprise AI Gateway",
  platformIcon: "⚡",

  // === Computed display values ===
  get displayName(): string {
    return this.orgName || `${this.platformIcon} ${this.platformName}`;
  },

  get headerTitle(): string {
    if (this.orgName) return this.orgName;
    return this.platformName;
  },

  get loginTitle(): string {
    if (this.orgName) return this.orgName;
    return `${this.platformIcon} ${this.platformName}`;
  },

  get loginSubtitle(): string {
    if (this.orgTagline) return this.orgTagline;
    if (this.orgName) return `Powered by ${this.platformName} ${this.productName}`;
    return this.productName;
  },

  get welcomeTitle(): string {
    if (this.orgName) return this.orgName;
    return this.platformName;
  },

  get welcomeSubtitle(): string {
    if (this.orgTagline) return this.orgTagline;
    return "Enterprise AI at your fingertips. Ask anything.";
  },

  get poweredBy(): string {
    return `Powered by ${this.platformName}`;
  },

  get hasOrgLogo(): boolean {
    return !!this.orgLogoUrl;
  },

  get hasOrgBranding(): boolean {
    return !!this.orgName;
  },
};
