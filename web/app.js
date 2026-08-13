const $ = (selector) => document.querySelector(selector);
const apiKeyInput = $("#apiKey");
const settingsDialog = $("#settingsDialog");
const generateButton = $("#generateButton");
const jobState = $("#jobState");
const progressBar = $("#progressBar");
const errorMessage = $("#errorMessage");
const player = $("#player");
const emptyState = $("#emptyState");
const downloadLink = $("#downloadLink");

function setHidden(element, hidden) {
  element.hidden = hidden;
  element.style.display = hidden ? "none" : "";
}

apiKeyInput.value = localStorage.getItem("h3_api_key") || "";

function headers() {
  const result = { "Content-Type": "application/json" };
  const key = localStorage.getItem("h3_api_key");
  if (key) result.Authorization = `Bearer ${key}`;
  return result;
}

async function readImage(input, shell) {
  const file = input.files[0];
  if (!file) {
    shell.classList.remove("has-image");
    return null;
  }
  const data = await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
  shell.querySelector("img").src = data;
  shell.classList.add("has-image");
  return data;
}

function readFile(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

function selectedFiles(id) {
  return Array.from($(id).files || []);
}

function updateReferenceSummary() {
  const groups = [
    ["#characterRefs", "角色"], ["#sceneRefs", "场景"], ["#itemRefs", "物品/画风"],
  ];
  const text = groups.map(([id, label]) => `${label} ${selectedFiles(id).length} 张`).join(" · ");
  $("#imageRefSummary").textContent = `${text} · 合计 ${groups.reduce((sum, [id]) => sum + selectedFiles(id).length, 0)} / 9`;
}

function setGenerationMode() {
  const mode = document.querySelector('input[name="generationMode"]:checked').value;
  const needsFrames = ["i2va", "fl2va", "l2va"].includes(mode);
  const needsReferences = mode === "ref2va";
  setHidden($("#frameInputs"), !needsFrames);
  setHidden($("#referenceInputs"), !needsReferences);
  setHidden($("#omniInputs"), !needsReferences);
  setHidden($("#firstUpload"), mode === "l2va");
  setHidden($("#lastUpload"), mode === "i2va");
  $("#firstUpload .upload-state").textContent = mode === "fl2va" ? "必选" : (mode === "i2va" ? "必选" : "不使用");
  $("#lastUpload .upload-state").textContent = mode === "fl2va" ? "必选" : (mode === "l2va" ? "必选" : "不使用");
}

$("#firstFrame").addEventListener("change", (event) => readImage(event.target, $("#firstUpload")));
$("#lastFrame").addEventListener("change", (event) => readImage(event.target, $("#lastUpload")));
document.querySelectorAll('input[name="generationMode"]').forEach((input) => input.addEventListener("change", setGenerationMode));
["#characterRefs", "#sceneRefs", "#itemRefs"].forEach((id) => $(id).addEventListener("change", updateReferenceSummary));
$("#settingsButton").addEventListener("click", () => settingsDialog.showModal());
$("#saveSettings").addEventListener("click", () => {
  localStorage.setItem("h3_api_key", apiKeyInput.value.trim());
});

async function poll(jobId) {
  for (;;) {
    await new Promise((resolve) => setTimeout(resolve, 2500));
    const response = await fetch(`/v1/videos/${jobId}`, { headers: headers() });
    if (!response.ok) throw new Error((await response.json()).detail || "查询任务失败");
    const job = await response.json();
    if (job.status === "completed") {
      const videoResponse = await fetch(job.content_url, { headers: headers() });
      if (!videoResponse.ok) throw new Error("视频下载失败");
      const videoUrl = URL.createObjectURL(await videoResponse.blob());
      if (player.src.startsWith("blob:")) URL.revokeObjectURL(player.src);
      player.src = videoUrl;
      player.classList.add("ready");
      setHidden(emptyState, true);
      downloadLink.href = videoUrl;
      setHidden(downloadLink, false);
      progressBar.style.width = "100%";
      jobState.textContent = `已完成 · ${job.requested_duration} 秒请求`;
      return;
    }
    if (job.status === "failed") throw new Error("生成失败，请查看服务日志");
    jobState.textContent = "正在生成";
    progressBar.style.width = "58%";
  }
}

generateButton.addEventListener("click", async () => {
  errorMessage.textContent = "";
  const prompt = $("#prompt").value.trim();
  if (!prompt) {
    errorMessage.textContent = "请先填写视频提示词";
    return;
  }
  if (!$("#acceptedTerms").checked) {
    errorMessage.textContent = "请先阅读并接受使用条款";
    return;
  }
  generateButton.disabled = true;
  setHidden(downloadLink, true);
  player.classList.remove("ready");
  setHidden(emptyState, false);
  jobState.textContent = "正在提交";
  progressBar.style.width = "12%";
  try {
    const generationMode = document.querySelector('input[name="generationMode"]:checked').value;
    const needsFrames = ["i2va", "fl2va", "l2va"].includes(generationMode);
    const needsReferences = generationMode === "ref2va";
    const firstFrame = ["i2va", "fl2va"].includes(generationMode)
      ? await readImage($("#firstFrame"), $("#firstUpload")) : null;
    const lastFrame = ["fl2va", "l2va"].includes(generationMode)
      ? await readImage($("#lastFrame"), $("#lastUpload")) : null;
    if (generationMode === "i2va" && !firstFrame) throw new Error("首帧生视频需要上传首帧");
    if (generationMode === "fl2va" && (!firstFrame || !lastFrame)) throw new Error("首尾帧生视频需要同时上传首帧和尾帧");
    if (generationMode === "l2va" && !lastFrame) throw new Error("尾帧生视频需要上传尾帧");
    const imageGroups = [
      ["#characterRefs", "character"], ["#sceneRefs", "scene"], ["#itemRefs", "item"],
    ];
    const imageFiles = needsReferences
      ? imageGroups.flatMap(([id, role]) => selectedFiles(id).map((file) => ({ file, role })))
      : [];
    if (needsReferences && imageFiles.length > 9) throw new Error("参考图总数不能超过 9 张");
    const videoFiles = needsReferences ? selectedFiles("#videoRefs") : [];
    const audioFiles = needsReferences ? selectedFiles("#audioRefs") : [];
    if (videoFiles.length > 3) throw new Error("参考视频不能超过 3 段");
    if (audioFiles.length > 3) throw new Error("参考音频不能超过 3 条");
    if (needsReferences && !imageFiles.length && !videoFiles.length && !audioFiles.length) {
      throw new Error("请至少上传一个参考素材");
    }
    const referenceImages = await Promise.all(imageFiles.map(async ({ file, role }) => ({
      data: await readFile(file), role, name: file.name.replace(/\.[^.]+$/, ""),
    })));
    const referenceVideos = await Promise.all(videoFiles.map(async (file) => ({
      data: await readFile(file), name: file.name.replace(/\.[^.]+$/, ""), use_audio: $("#useVideoAudio").checked,
    })));
    const referenceAudios = await Promise.all(audioFiles.map(async (file) => ({
      data: await readFile(file), name: file.name.replace(/\.[^.]+$/, ""),
    })));
    const payload = {
      prompt,
      duration: Number($("#duration").value),
      aspect_ratio: $("#aspectRatio").value,
      preset: document.querySelector('input[name="preset"]:checked').value,
      generation_mode: generationMode,
      prompt_mode: "jimeng",
      first_frame: needsFrames && generationMode !== "l2va" ? firstFrame : null,
      last_frame: needsFrames && generationMode !== "i2va" ? lastFrame : null,
      reference_images: needsReferences ? referenceImages : [],
      reference_videos: needsReferences ? referenceVideos : [],
      reference_audios: needsReferences ? referenceAudios : [],
      reference_image_size: $("#referenceImageSize").value,
      accepted_terms: true,
    };
    const response = await fetch("/v1/videos", {
      method: "POST",
      headers: headers(),
      body: JSON.stringify(payload),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "提交失败");
    jobState.textContent = `已排队 · ${result.requested_duration} 秒请求`;
    progressBar.style.width = "30%";
    await poll(result.id);
  } catch (error) {
    errorMessage.textContent = error.message;
    jobState.textContent = "任务未完成";
    progressBar.style.width = "0";
  } finally {
    generateButton.disabled = false;
  }
});

fetch("/health")
  .then((response) => response.json())
  .then(() => { $("#serviceState").textContent = "服务已连接"; })
  .catch(() => { $("#serviceState").textContent = "服务未连接"; });

setGenerationMode();
setHidden(downloadLink, true);
updateReferenceSummary();
