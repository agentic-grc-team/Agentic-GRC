export class AssessmentPage {
  constructor(page) {
    this.page = page;
  }

  async open() {
    await this.page.getByRole("button", { name: "Assessments" }).click();
  }

  async create(title) {
    await this.page.getByRole("textbox", { name: "New assessment title" }).fill(title);
    await this.page.getByRole("button", { name: "Create assessment" }).click();
  }
}
