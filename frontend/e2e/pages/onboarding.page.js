export class OnboardingPage {
  constructor(page) {
    this.page = page;
  }

  async createOrganization(name) {
    await this.page.getByLabel(/Organization name/).fill(name);
    await this.page.getByLabel(/Sector/).selectOption("healthcare");
    await this.page.getByLabel(/Organization size/).selectOption("mid-market");
    await this.page.getByRole("button", { name: /Create workspace/ }).click();
  }

  async invite(email, role = "consultant") {
    await this.page.getByLabel("Teammate email address").fill(email);
    await this.page.getByLabel("Role").selectOption(role);
    await this.page.getByRole("button", { name: /Send invitation/ }).click();
  }

  async acceptInvitation() {
    await this.page.getByRole("button", { name: "Accept" }).click();
  }
}
