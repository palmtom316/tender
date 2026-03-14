const milestones = [
  "项目上传与解析",
  "否决项复核",
  "章节生成与审校",
  "模板导出",
];

export function App() {
  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">AI Tender Console</p>
        <h1>技术标智能编制系统</h1>
        <p className="subtitle">
          React + Vite 初始化完成。后续页面将围绕解析、复核、生成、审校和导出主链路展开。
        </p>
      </section>
      <section className="cards">
        {milestones.map((item, index) => (
          <article className="card" key={item}>
            <span className="index">0{index + 1}</span>
            <h2>{item}</h2>
            <p>已预留工程壳，等待接入业务 API 与页面路由。</p>
          </article>
        ))}
      </section>
    </main>
  );
}

