const analyzeButton = document.getElementById("analyze-button");
const organizationInput = document.getElementById("organization-name");
const evidenceFileInput = document.getElementById("evidence-file");
const evidenceDescriptionInput = document.getElementById("evidence-description");
const findingSection = document.getElementById("finding-section");
const findingMessage = document.getElementById("finding-message");

analyzeButton.addEventListener("click", function() {
    const organizationName = organizationInput.value.trim();
    const selectedAnswer = document.querySelector('input[name="answer"]:checked');

    if (organizationName === ""){
        findingMessage.textContent = "Please enter organization name";
        findingSection.style.borderLeftColor = "#dc2626";
        findingSection.style.backgroundColor = "#fee2e2";
        return;
    }

    if (selectedAnswer === null){
        findingMessage.textContent = "Please select an answer before generating a finding";
        findingSection.style.borderLeftColor = "#dc2626";
        findingSection.style.backgroundColor = "#fee2e2";
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
        backgroundColor = "#fef3c7";

    } else if (answer === "unsure"){
        status = "INSUFFICIENT INFORMATION";
        message =
            "The organization could not confirm whether all " +
            "administrator accounts use multi-factor authentication.";
        color = "#64748b";
        backgroundColor = "#f1f5f9";

    } else if (answer === "yes" && evidenceDescription === "" && fileCheck === false){
        status = "INSUFFICIENT EVIDENCE";
        message =
            "The organization claims that multi-factor authentication " +
            "is enabled, but no supporting evidence was provided.";
        color = "#f59e0b";
        backgroundColor = "#fef3c7";

    } else {
        status = "PENDING HUMAN REVIEW";
        message =
            "The organization claims that multi-factor authentication " +
            "is enabled and supporting evidence was provided. " +
            "The evidence must be reviewed before the control can be " +
            "marked as satisfied.";
        color = "#2563eb";
        backgroundColor = "#dbeafe";
    }

    findingMessage.innerHTML = "<strong>Organization:</strong> " + organizationName +
                "<br><br>" + "<strong>Status:</strong> " + status +
                "<br><br>" + "<strong>Finding:</strong> " + message;

    findingSection.style.borderLeftColor = color;
    findingSection.style.backgroundColor = backgroundColor;         

})
