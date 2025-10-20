// static/main.js

let items = [];
let idx = 0;
let direction = "fr2nl";

// ---- BUTTON HANDLERS ----

document.getElementById("stopBtn").onclick = () => {
  items = [];
  idx = 0;
  document.getElementById("quiz").style.display = "none";
  alert("🛑 Practice stopped. You can start again anytime!");
};

// When you click "Initialize DB / Load vocab"
document.getElementById("initBtn").onclick = async () => {
  const r = await fetch("/api/init", {method:"POST"}).then(r=>r.json());
  alert("✅ Database initialized and vocab loaded!");
};

// When you click "Start Diagnostic"
document.getElementById("diagBtn").onclick = async () => {
  direction = document.getElementById("direction").value;
  const r = await fetch("/api/diagnostic").then(r=>r.json());
  items = r.items;
  idx = 0;
  showQuiz();
};

// When you click "Start Adaptive Practice"
document.getElementById("adaptiveBtn").onclick = async () => {
  direction = document.getElementById("direction").value;
  const r = await fetch("/api/adaptive?n=10").then(r=>r.json());
  items = r.items;
  idx = 0;
  showQuiz();
};

// When you click "Show Progress"
document.getElementById("progressBtn").onclick = async () => {
  const r = await fetch("/api/progress").then(r=>r.json());
  const data = r.rows;
let html = "<table><tr><th>French</th><th>Dutch</th><th>Status</th><th>Score</th></tr>";
data.forEach(row => {
  html += `<tr>
    <td>${row.fr}</td>
    <td>${row.nl}</td>
    <td>${row.bucket}</td>
    <td>${row.correct_count}/${row.total_tests}</td>
  </tr>`;
});
html += "</table>";
document.getElementById("progressText").innerHTML = html;
document.getElementById("progress").style.display = "block";
document.getElementById("hideProgressBtn").onclick = () => {
  document.getElementById("progress").style.display = "none";
};

};

// When you click "Export CSV"
document.getElementById("exportBtn").onclick = () => {
  window.location = "/api/export";
};

// ---- QUIZ LOGIC ----

function showQuiz(){
  document.getElementById("quiz").style.display = "block";
  document.getElementById("progress").style.display = "none";
  showQuestion();
}

async function showQuestion(){
  const qnum = idx + 1;

  // If we've finished all items, automatically fetch new ones
  if(idx >= items.length){
    document.getElementById("prompt").textContent = "Loading more words...";
    document.getElementById("qnum").textContent = "Fetching new set 🔄";

    const r = await fetch(`/api/adaptive?n=10`).then(r=>r.json());
    items = r.items;
    idx = 0;
    setTimeout(showQuestion, 1000); // small delay so it feels natural
    return;
  }

  const it = items[idx];
  document.getElementById("qnum").textContent = `Question ${qnum} / ${items.length}`;
  const promptText = (direction === "fr2nl") ? it.fr : it.nl;
  document.getElementById("prompt").textContent = promptText;
  document.getElementById("answer").value = "";
  document.getElementById("feedback").textContent = "";
}

// When you click "Submit"
document.getElementById("submitBtn").onclick = async () => {
  if(idx >= items.length) return;
  const it = items[idx];
  const payload = {
    id: it.id,
    answer: document.getElementById("answer").value,
    confidence: document.getElementById("confidence").value,
    direction: direction
  };
  const r = await fetch("/api/answer", {
    method:"POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify(payload)
  }).then(r=>r.json());
  if(r.error){
    document.getElementById("feedback").textContent = "Error: " + r.error;
    return;
  }
  const fb = r.correct ? "✅ Correct" : "❌ Incorrect";
  document.getElementById("feedback").textContent =
    `${fb}. Correct: ${r.correct_text}. New bucket: ${r.new_bucket}`;
  idx++;
  setTimeout(showQuestion, 4000);
};

// When you click "Hint"
document.getElementById("hintBtn").onclick = () => {
  if(idx >= items.length) return;
  const it = items[idx];
  const text = (direction === "fr2nl") ? it.nl : it.fr;
  const first = text.trim().split(/\s+/)[0].charAt(0);
  document.getElementById("feedback").textContent = `💡 Hint: starts with "${first}"`;
};

// When you click "Skip"
document.getElementById("skipBtn").onclick = async () => {
  if(idx >= items.length) return;
  const it = items[idx];
  const payload = { id: it.id, answer: "", confidence: 1, direction: direction };
  const r = await fetch("/api/answer", {
    method:"POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify(payload)
  }).then(r=>r.json());
  document.getElementById("feedback").textContent =
    `⏭️ Skipped. Marked: ${r.new_bucket}. Correct: ${r.correct_text}`;
  idx++;
  setTimeout(showQuestion, 4000);
};

