import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import ReactDOM from "react-dom/client";
import "./style.css";
import "./premium.css";

type Metric = "soil_moisture" | "soil_moisture_raw_adc" | "temperature_c" | "humidity" | "light_percent" | "light_raw_adc" | "tds_ppm";
type Reading = { id: string; device_id: string; soil_moisture: number | null; soil_moisture_raw_adc: number | null; temperature_c: number; humidity: number; light_lux: number | null; light_raw_adc: number | null; light_percent: number | null; tds_ppm: number; recorded_at: string };
type Profile = { id?: string; plant_name: string; species: string; plant_type: string; planting_date: string; description: string; device_id: string };
type Latest = { reading: Reading | null; connection_status: "online" | "offline" | "never_connected"; last_updated: string | null; plant_health: { status: string; message: string } };
type Page = "Overview" | "My Plant" | "Analytics" | "AI Plant Adviser" | "Care History";
const api = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1").replace(/\/$/, "");
const pages: Page[] = ["Overview", "My Plant", "Analytics", "AI Plant Adviser", "Care History"];
const metrics: { key: Metric; title: string; unit: string; color: string }[] = [
  { key: "soil_moisture", title: "Soil moisture", unit: "%", color: "#5b966d" },
  { key: "soil_moisture_raw_adc", title: "Soil raw ADC", unit: "ADC", color: "#5b966d" },
  { key: "temperature_c", title: "Temperature", unit: "°C", color: "#dc9360" },
  { key: "humidity", title: "Air humidity", unit: "%", color: "#75a6c6" },
  { key: "light_percent", title: "Light (relative %)", unit: "%", color: "#d4b04f" },
  { key: "light_raw_adc", title: "Light (raw ADC)", unit: "ADC", color: "#d4b04f" },
  { key: "tds_ppm", title: "Approx. TDS · soil-water extract", unit: "ppm", color: "#9a84bd" },
];
const initialProfile: Profile = { plant_name: "", species: "", plant_type: "houseplant", planting_date: "", description: "", device_id: "" };
const suggestions = ["Why are my plant leaves turning yellow?", "Does my plant need watering?", "How can I improve plant growth?", "Explain my current sensor readings.", "আমার গাছের যত্ন কীভাবে নেব?", "আমার গাছের পাতা হলুদ হচ্ছে কেন?"];

function App() {
  const [page, setPage] = useState<Page>("Overview");
  const [latest, setLatest] = useState<Latest | null>(null);
  const [history, setHistory] = useState<Reading[]>([]);
  const [profile, setProfile] = useState<Profile>(initialProfile);
  const [profileSaved, setProfileSaved] = useState(false);
  const [range, setRange] = useState("24h");
  const [selected, setSelected] = useState<Metric>("soil_moisture_raw_adc");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [language, setLanguage] = useState<"en" | "bn">("en");
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<{ role: "user" | "assistant"; text: string }[]>([]);
  const [weekly, setWeekly] = useState("");
  const [aiConfigured, setAiConfigured] = useState(false);
  const refresh = useCallback(async () => {
    try {
      const hours = range === "6h" ? 6 : range === "7d" ? 168 : 24;
      const since = new Date(Date.now() - hours * 3600000).toISOString();
      const [current, rows] = await Promise.all([fetch(`${api}/dashboard/latest`), fetch(`${api}/dashboard/readings?since=${encodeURIComponent(since)}&limit=500`)]);
      if (!current.ok || !rows.ok) throw new Error("Dashboard readings are unavailable.");
      setLatest(await current.json());
      setHistory((await rows.json()).reverse());
      setError("");
    } catch { setError("Could not reach the PlantMate API. Check the backend connection."); }
  }, [range]);
  useEffect(() => { void refresh(); const timer = window.setInterval(() => void refresh(), 8000); return () => clearInterval(timer); }, [refresh]);
  useEffect(() => {
    void fetch(`${api}/plants/profile`).then(async (r) => { if (r.ok) { const data = await r.json(); setProfile({ ...initialProfile, ...data, planting_date: data.planting_date ?? "", description: data.description ?? "" }); setProfileSaved(true); } });
    void fetch(`${api}/ai/status`).then((r) => r.ok ? r.json() : null).then((x) => setAiConfigured(Boolean(x?.configured))).catch(() => setAiConfigured(false));
  }, []);
  const current = latest?.reading ?? null;
  const metric = metrics.find((item) => item.key === selected) ?? metrics[0];
  const chartMetrics = useMemo(() => {
    const available = metrics.filter((item) =>
      history.some((reading) => reading[item.key] !== null && reading[item.key] !== undefined),
    );
    return available.length ? available : metrics;
  }, [history]);
  useEffect(() => {
    if (history.length && !chartMetrics.some((item) => item.key === selected)) {
      setSelected(chartMetrics[0].key);
    }
  }, [chartMetrics, history.length, selected]);
  const chartData = useMemo(() => history.filter((r) => r[selected] !== null && r[selected] !== undefined).map((r) => ({ value: r[selected] as number, time: r.recorded_at })), [history, selected]);
  const stats = useMemo(() => {
    if (!chartData.length) return null;
    const vals = chartData.map((x) => x.value); return { latest: vals[vals.length - 1], min: Math.min(...vals), max: Math.max(...vals), avg: vals.reduce((a, b) => a + b, 0) / vals.length };
  }, [chartData]);
  const value = (key: Metric) => current?.[key] ?? null;
  async function saveProfile(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try { const r = await fetch(`${api}/plants/profile`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...profile, planting_date: profile.planting_date || null, description: profile.description || null }) }); if (!r.ok) throw new Error((await r.json()).detail ?? "Could not save plant profile."); setProfile({ ...profile, ...(await r.json()) }); setProfileSaved(true); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not save plant profile."); } finally { setBusy(false); }
  }
  async function sendQuestion(text = question) {
    const prompt = text.trim(); if (!prompt) return;
    setMessages((m) => [...m, { role: "user", text: prompt }]); setQuestion(""); setBusy(true); setError("");
    try { const r = await fetch(`${api}/ai/chat`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: prompt, language }) }); const data = await r.json(); if (!r.ok) throw new Error(data.detail ?? "The adviser is unavailable."); setMessages((m) => [...m, { role: "assistant", text: data.answer }]); }
    catch (e) { const text = e instanceof Error ? e.message : "The adviser is unavailable."; setMessages((m) => [...m, { role: "assistant", text: `I couldn't answer just now: ${text}` }]); }
    finally { setBusy(false); }
  }
  async function requestWeekly() {
    setBusy(true); setError(""); try { const r = await fetch(`${api}/ai/weekly-summary?language=${language}`, { method: "POST" }); const data = await r.json(); if (!r.ok) throw new Error(data.detail ?? "Summary unavailable."); setWeekly(data.readings_count ? data.summary : "No stored sensor readings are available for this week."); } catch (e) { setError(e instanceof Error ? e.message : "Summary unavailable."); } finally { setBusy(false); }
  }
  function renderChart() {
    if (!chartData.length) return <div className="pm-empty"><span>🌱</span><strong>No readings for this period</strong><p>Charts will appear when stored ESP32 readings are available.</p></div>;
    const min = Math.min(...chartData.map((x) => x.value)); const max = Math.max(...chartData.map((x) => x.value)); const spread = max - min || 1;
    const points = chartData.map((x, i) => `${18 + i * 824 / Math.max(1, chartData.length - 1)},${188 - (x.value - min) / spread * 160}`).join(" ");
    return <><svg className="pm-chart" viewBox="0 0 860 210" role="img" aria-label={`${metric.title} historical chart`}><polyline points={points} fill="none" stroke={metric.color} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"/></svg><div className="pm-chart-axis"><span>{time(chartData[0].time)}</span><span>{time(chartData[chartData.length - 1].time)}</span></div></>;
  }
  return <div className="pm-app">
    <header className="pm-header"><a className="pm-brand" onClick={() => setPage("Overview")}><span>✿</span><span>PlantMate<small>SEARCH SMARTER. GROW BETTER.</small></span></a><div className="pm-device"><i className={latest?.connection_status ?? ""}/>{statusText(latest?.connection_status)}<button onClick={() => void refresh()} aria-label="Refresh readings">↻</button></div></header>
    <nav className="pm-nav" aria-label="Main navigation">{pages.map((p) => <button key={p} className={page === p ? "active" : ""} onClick={() => setPage(p)}>{p}</button>)}</nav>
    <main className="pm-main"><div className="pm-page-head"><div><p className="pm-kicker">YOUR BOTANICAL SPACE</p><h1>{page === "Overview" ? "A clearer view of your garden." : page}</h1><p>Real sensor readings and practical care, grounded in your garden.</p></div><div className="pm-updated">LAST READING<strong>{time(latest?.last_updated)}</strong></div></div>
      {error && <div className="pm-error" role="alert">{error}<button onClick={() => setError("")}>Dismiss</button></div>}
      {page === "Overview" && <>
        <section className="pm-cards" aria-label="Latest sensor readings">
          <Card name={current?.soil_moisture == null ? "Soil probe · raw ADC" : "Soil moisture"} val={current?.soil_moisture ?? current?.soil_moisture_raw_adc ?? null} unit={current?.soil_moisture == null ? "ADC" : "%"} note={current?.soil_moisture == null ? "Uncalibrated; not a percentage" : "Calibrated probe reading"}/>
          <Card name="Temperature" val={value("temperature_c")} unit="°C" note="DHT22 ambient air"/><Card name="Air humidity" val={value("humidity")} unit="%" note="DHT22 measurement"/>
          <Card name="LDR · raw ADC" val={value("light_raw_adc")} unit="ADC" note={current?.light_percent == null ? "Relative light unavailable" : `Relative light: ${current.light_percent.toFixed(1)}%`}/>
          <Card name="Approx. TDS · soil-water extract" val={value("tds_ppm")} unit="ppm" note="Not direct soil EC or NPK"/>
        </section>
        <section className="pm-grid"><article className="pm-panel"><PanelTitle title="Recent sensor history" copy="Updates automatically every 8 seconds."/><div className="pm-controls"><select aria-label="Chart measurement" value={selected} onChange={(e) => setSelected(e.target.value as Metric)}>{chartMetrics.map((m) => <option value={m.key} key={m.key}>{m.key.endsWith("raw_adc") ? m.title : `${m.title} (${m.unit})`}</option>)}</select><Range range={range} setRange={setRange}/></div>{renderChart()}</article><article className="pm-panel"><PanelTitle title={profile.plant_name || "Your plant"} copy={profile.species || "Add a plant profile for tailored context."}/><div className="pm-care"><span className={`pm-health ${latest?.plant_health.status ?? "unavailable"}`}>{latest?.plant_health.status ?? "unavailable"}</span><p>{latest?.plant_health.message ?? "Care insights need sensor readings."}</p></div><button className="pm-link" onClick={() => setPage("My Plant")}>Edit plant profile →</button><div className="pm-tds-note">TDS is approximate from soil-water extract and does not measure NPK.</div></article></section>
      </>}
      {page === "My Plant" && <form className="pm-panel pm-form" onSubmit={saveProfile}><PanelTitle title="Plant profile" copy="This public demo profile provides context for care advice."/>{([["plant_name","Plant name"],["species","Plant species"],["plant_type","Plant type"],["planting_date","Planting date"],["device_id","Associated device ID"]] as const).map(([key,label])=><label key={key}>{label}<input required={key!=="planting_date"} type={key==="planting_date"?"date":"text"} maxLength={120} value={profile[key]} onChange={(e)=>setProfile({...profile,[key]:e.target.value})}/></label>)}<label className="pm-wide">Description<textarea maxLength={2000} value={profile.description} onChange={(e)=>setProfile({...profile,description:e.target.value})}/></label><button className="pm-primary" disabled={busy}>{busy?"Saving…":profileSaved?"Save changes":"Save plant profile"}</button></form>}
      {page === "Analytics" && <section className="pm-panel"><PanelTitle title="Environmental analytics" copy="Statistics use only readings stored in PlantMate."/><div className="pm-controls"><select aria-label="Analytics measurement" value={selected} onChange={(e)=>setSelected(e.target.value as Metric)}>{chartMetrics.map((m)=><option key={m.key} value={m.key}>{m.key.endsWith("raw_adc") ? m.title : `${m.title} (${m.unit})`}</option>)}</select><Range range={range} setRange={setRange}/></div>{renderChart()}<div className="pm-stats">{[["Latest",stats?.latest],["Minimum",stats?.min],["Maximum",stats?.max],["Average",stats?.avg]].map(([label,n])=><div key={String(label)}><small>{label}</small><strong>{typeof n==="number"?`${n.toLocaleString(undefined,{maximumFractionDigits:1})} ${metric.unit}`:"—"}</strong></div>)}</div></section>}
      {page === "Care History" && <section className="pm-panel"><PanelTitle title="Care history" copy="No care events are inferred or fabricated."/>{history.length? <div className="pm-history">{[...history].reverse().slice(0,40).map((r)=><article key={r.id}><time>{time(r.recorded_at)}</time><strong>Sensor reading received</strong><p>{r.soil_moisture==null?`Soil probe ${r.soil_moisture_raw_adc ?? "—"} ADC · uncalibrated`:`Soil moisture ${r.soil_moisture}%`} · {r.temperature_c} °C · humidity {r.humidity}%</p></article>)}</div>:<div className="pm-empty"><span>🌿</span><strong>No stored readings yet</strong><p>Care history will appear after real device readings arrive.</p></div>}</section>}
      {page === "AI Plant Adviser" && <section className="pm-ai-layout"><article className="pm-panel pm-chat"><div className="pm-chat-head"><PanelTitle title="Ask your plant adviser" copy={aiConfigured?`Grounded in ${profile.species || "your plant profile"} and stored sensor readings.`:"Add GEMINI_API_KEY to the backend environment to enable live answers."}/><select value={language} onChange={(e)=>setLanguage(e.target.value as "en"|"bn")} aria-label="Response language"><option value="en">English</option><option value="bn">বাংলা</option></select></div><div className="pm-messages">{messages.length?messages.map((m,i)=><div className={`pm-message ${m.role}`} key={`${i}-${m.role}`}><span>{m.role==="user"?"You":"PlantMate adviser"}</span><p>{m.text}</p></div>):<div className="pm-empty"><span>✿</span><strong>Your garden-aware adviser</strong><p>Responses use your selected plant and actual stored readings. Missing calibration remains explicit.</p></div>}{busy&&<div className="pm-thinking" role="status">Thinking with your garden data…</div>}</div><div className="pm-suggestions">{suggestions.map((s)=><button key={s} onClick={()=>void sendQuestion(s)} disabled={busy}>{s}</button>)}</div><form className="pm-compose" onSubmit={(e)=>{e.preventDefault();void sendQuestion();}}><textarea value={question} maxLength={2000} onChange={(e)=>setQuestion(e.target.value)} placeholder="Ask about your plant…"/><button className="pm-primary" disabled={busy||!question.trim()}>Send</button></form></article><aside className="pm-panel pm-summary"><PanelTitle title="Weekly garden note" copy="Generated only from readings stored in the last seven days."/><button className="pm-primary" disabled={busy} onClick={()=>void requestWeekly()}>{busy?"Preparing…":"Create weekly summary"}</button>{weekly&&<p className="pm-summary-text">{weekly}</p>}<p className="pm-disclaimer">AI advice is informational. It does not diagnose plant disease. Raw ADC is not moisture percent or lux; TDS is not EC or NPK.</p></aside></section>}
      <footer className="pm-footer">PlantMate · Search smarter. Grow better. <span>Live data refreshes every 8 seconds</span></footer>
    </main>
  </div>;
}
function Card({name,val,unit,note}:{name:string;val:number|null;unit:string;note:string}){return <article className="pm-card"><span>{name}</span><strong>{val==null?"—":val.toLocaleString(undefined,{maximumFractionDigits:1})}<small>{val==null?"":unit}</small></strong><p>{note}</p></article>}
function PanelTitle({title,copy}:{title:string;copy:string}){return <div className="pm-panel-title"><h2>{title}</h2><p>{copy}</p></div>}
function Range({range,setRange}:{range:string;setRange:(s:string)=>void}){return <div className="pm-range">{["6h","24h","7d"].map((r)=><button key={r} className={range===r?"active":""} onClick={()=>setRange(r)}>{r}</button>)}</div>}
function time(s:string|null|undefined){return s?new Intl.DateTimeFormat(undefined,{dateStyle:"medium",timeStyle:"short"}).format(new Date(s)):"No readings yet"}
function statusText(s:string|undefined){return s==="online"?"ESP32 online":s==="offline"?"ESP32 offline":"Awaiting ESP32"}

ReactDOM.createRoot(document.getElementById("root")!).render(<App/>);
