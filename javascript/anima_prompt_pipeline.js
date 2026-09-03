function anima_send_to(tab) {
    if (typeof gradioApp !== "function" || typeof updateInput !== "function") {
        return;
    }
    const app = gradioApp();
    const sourcePrompt = app.querySelector("#anima_prompt_out textarea");
    const sourceNeg = app.querySelector("#anima_negative_out textarea");
    const prompt = sourcePrompt ? (sourcePrompt.value || "") : "";
    if (!prompt) {
        return;
    }
    const negative = sourceNeg ? (sourceNeg.value || "") : "";

    const p = app.querySelector("#" + tab + "_prompt textarea");
    const n = app.querySelector("#" + tab + "_neg_prompt textarea");
    if (p) {
        p.value = prompt;
        updateInput(p);
    }
    if (n) {
        n.value = negative;
        updateInput(n);
    }

    const tabs = app.querySelector("#tabs");
    const buttons = tabs ? tabs.querySelectorAll("button") : [];
    if (tab === "txt2img") {
        if (typeof switch_to_txt2img === "function") switch_to_txt2img();
        else if (buttons[0]) buttons[0].click();
    } else {
        if (typeof switch_to_img2img === "function") switch_to_img2img();
        else if (buttons[1]) buttons[1].click();
    }
}

function anima_attach_send_listeners() {
    if (typeof gradioApp !== "function") {
        return;
    }
    const app = gradioApp();
    const sendTxt = app.getElementById("anima_send_txt2img");
    const sendImg = app.getElementById("anima_send_img2img");
    if (sendTxt) sendTxt.onclick = () => anima_send_to("txt2img");
    if (sendImg) sendImg.onclick = () => anima_send_to("img2img");
}

if (typeof onUiLoaded === "function") {
    onUiLoaded(anima_attach_send_listeners);
}
if (typeof onUiTabChange === "function") {
    onUiTabChange(anima_attach_send_listeners);
}
