export class LoginPage {
  constructor(page) {
    this.page = page;
  }

  async open() {
    await this.page.goto("/");
  }

  async signIn(email = "admin@example.test", password = "e2e-password") {
    await this.page.getByLabel("Email address").fill(email);
    await this.page.getByLabel("Password").fill(password);
    await this.page.getByRole("button", { name: "Sign in" }).click();
  }
}
