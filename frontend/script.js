const $ = (sel) => document.querySelector(sel);
let token = localStorage.getItem("token") || "";

function setAuthStatus() {
  $("#authStatus").textContent = token ? "Autenticado" : "No autenticado";
}
setAuthStatus();

// ----- Modal Auth -----
const modal = document.getElementById("authModal");
document.getElementById("btnShowAuth").addEventListener("click", () => {
  modal.classList.remove("hidden");
  modal.classList.add("flex");
});

document.getElementById("btnSignup").addEventListener("click", async () => {
  const email = document.getElementById("authEmail").value.trim();
  const password = document.getElementById("authPass").value.trim();
  if (!email || !password) return;

  const fd = new URLSearchParams();
  fd.append("username", email);
  fd.append("password", password);

  const res = await fetch("/auth/signup", { method: "POST", body: fd });
  const data = await res.json();
  document.getElementById("authMsg").textContent =
    data.ok ? "Usuario creado. Ahora inicia sesión." : (data.detail || "Error");
});

document.getElementById("btnLogin").addEventListener("click", async () => {
  const email = document.getElementById("authEmail").value.trim();
  const password = document.getElementById("authPass").value.trim();
  if (!email || !password) return;

  const fd = new URLSearchParams();
  fd.append("username", email);
  fd.append("password", password);

  const res = await fetch("/auth/login", { method: "POST", body: fd });
  const data = await res.json();
  if (data.access_token) {
    token = data.access_token;
    localStorage.setItem("token", token);
    document.getElementById("authMsg").textContent = "Sesión iniciada.";
    modal.classList.add("hidden");
    modal.classList.remove("flex");
    setAuthStatus();
  } else {
    document.getElementById("authMsg").textContent = data.detail || "Error al iniciar sesión.";
  }
});

// ----- Subir -----
document.getElementById("btnUpload").addEventListener("click", async () => {
  if (!token) { alert("Inicia sesión primero."); return; }
  const files = document.getElementById("fileInput").files;
  if (!files || files.length === 0) {
    document.getElementById("uploadStatus").textContent = "Selecciona al menos un archivo.";
    return;
  }
  const fd = new FormData();
  for (const f of files) fd.append("files", f);

  document.getElementById("uploadStatus").textContent = "Subiendo...";
  const res = await fetch("/api/upload", {
    method: "POST",
    body: fd,
    headers: { "Authorization": "Bearer " + token }
  });
  const data = await res.json();
  document.getElementById("uploadStatus").textContent =
    data.ok ? `Subidos: ${data.saved.join(", ")}` : (data.detail || "Error al subir.");
});

// ----- Ingestar -----
document.getElementById("btnIngest").addEventListener("click", async () => {
  if (!token) { alert("Inicia sesión primero."); return; }
  document.getElementById("ingestStatus").textContent = "Ingestando (indexando chunks)...";
  const res = await fetch("/api/ingest", {
    method: "POST",
    headers: { "Authorization": "Bearer " + token }
  });
  const data = await res.json();
  document.getElementById("ingestStatus").textContent =
    data.ok ? `Listo. Chunks indexados: ${data.chunks_indexed}` : (data.detail || "Error en ingesta.");
});

// ----- Preguntar -----
document.getElementById("btnAsk").addEventListener("click", async () => {
  if (!token) { alert("Inicia sesión primero."); return; }
  const q = document.getElementById("query").value.trim();
  if (!q) return;
  document.getElementById("answer").textContent = "Pensando...";
  const res = await fetch("/api/ask", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": "Bearer " + token
    },
    body: JSON.stringify({ query: q }),
  });
  const data = await res.json();
  document.getElementById("answer").textContent =
    data.ok ? data.answer : (data.error || data.detail || "Error al consultar.");
});
