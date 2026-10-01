const analyzeButton = document.getElementById("analyze-button");
const organizationInput = document.getElementById("organization-name");
const evidenceFileInput = document.getElementById("evidence-file");
const evidenceDescriptionInput = document.getElementById("evidence-description");
const findingSection = document.getElementById("finding-section");
const findingMessage = document.getElementById("finding-message");

const moduleDashboard = document.getElementById("module-dashboard");
const assessmentWorkspace = document.getElementById("assessment-workspace");
const selectedModuleName = document.getElementById("selected-module-name");
const backButton = document.getElementById("back-button");
const moduleCards = document.querySelectorAll(".module-card");

let activeModuleCard = null;


for (let i = 0; i < moduleCards.length; i++) {

    moduleCards[i].addEventListener("click", function() {

        activeModuleCard = moduleCards[i];

        const moduleName = activeModuleCard.dataset.module;

        selectedModuleName.textContent = moduleName;

        const moduleStatus =
            activeModuleCard.querySelector(".module-status");

        if (moduleStatus.textContent === "Not started") {
            moduleStatus.textContent = "In progress";
            moduleStatus.classList.add("in-progress");
}

        moduleDashboard.hidden = true;
        assessmentWorkspace.hidden = false;
    });
}


backButton.addEventListener("click", function() {
    assessmentWorkspace.hidden = true;
    moduleDashboard.hidden = false;
});

analyzeButton.addEventListener("click", function() {
    const organizationName = organizationInput.value.trim();
    const selectedAnswer = document.querySelector('input[name="answer"]:checked');

    if (organizationName === ""){
        findingMessage.textContent = "Please enter organization name";
        findingSection.style.borderLeftColor = "#dc2626";
        findingSection.style.backgroundColor = "#2a151d";
        return;
    }

    if (selectedAnswer === null){
        findingMessage.textContent = "Please select an answer before generating a finding";
        findingSection.style.borderLeftColor = "#dc2626";
        findingSection.style.backgroundColor = "#2a151d";
        return;
    }

    const answer = selectedAnswer.value;
    const evidenceDescription = evidenceDescriptionInput.value.trim();
    const fileCheck = evidenceFileInput.files.length > 0;

    let status = "";
    let message = "";
    let color = "";
    let backgroundColor = "";

    if (answer === "no"){
        status = "NOT SATISFIED";
        message =
            "Administrator accounts do not use mandatory " +
            "multi-factor authentication. This creates a high risk " +
            "of unauthorized privileged access.";

        color = "#dc2626";
        backgroundColor = "#fee2e2";

    } else if (answer === "partial"){
        status = "PARTIALLY SATISFIED";
        message = 
            "Multi-factor authentication is implemented only for " +
            "some administrator accounts. All privileged accounts " +
            "should be protected.";
        color = "#f59e0b";
        backgroundColor = "#2a2111";

    } else if (answer === "unsure"){
        status = "INSUFFICIENT INFORMATION";
        message =
            "The organization could not confirm whether all " +
            "administrator accounts use multi-factor authentication.";
        color = "#64748b";
        backgroundColor = "#1b2330";

    } else if (answer === "yes" && evidenceDescription === "" && fileCheck === false){
        status = "INSUFFICIENT EVIDENCE";
        message =
            "The organization claims that multi-factor authentication " +
            "is enabled, but no supporting evidence was provided.";
        color = "#f59e0b";
        backgroundColor = "#2a2111"

    } else {
        status = "PENDING HUMAN REVIEW";
        message =
            "The organization claims that multi-factor authentication " +
            "is enabled and supporting evidence was provided. " +
            "The evidence must be reviewed before the control can be " +
            "marked as satisfied.";
        color = "#2563eb";
        backgroundColor = "#102536";
    }

    findingMessage.innerHTML = "<strong>Organization:</strong> " + organizationName +
                "<br><br>" + "<strong>Status:</strong> " + status +
                "<br><br>" + "<strong>Finding:</strong> " + message;

    findingSection.style.borderLeftColor = color;
    findingSection.style.backgroundColor = backgroundColor;         

})
