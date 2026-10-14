"""Fixed interview setups for evals. Fictional candidates; mixed languages,
roles and interviewer styles so results are not tuned to one case."""

from app.interview.models import InterviewConfig

SCENARIOS: dict[str, InterviewConfig] = {
    "backend_zh": InterviewConfig(
        job_title="后端开发工程师",
        language="zh",
        persona="neutral",
        interviewer_role="tech_lead",
        difficulty="intermediate",
        duration_min=15,
        resume_text=(
            "王浩，3 年后端经验。\n"
            "订单系统重构（Go, Kafka, MySQL, Redis）：负责把单体拆成订单、库存、支付三个服务；"
            "下单改为先写 Kafka 再异步落库，库存用 Redis Lua 预扣减，下单接口 P99 从 800ms 降到 120ms。\n"
            "监控平台：基于 Prometheus + Grafana，负责告警规则引擎，误报率下降 60%。\n"
            "技能：Go, Python, MySQL, Redis, Kafka, Docker, Kubernetes"
        ),
        job_description="高并发交易系统后端开发。要求：熟悉 Go 或 Java；熟悉分布式系统、消息队列、缓存；有高可用和性能优化经验；了解 Kubernetes。",
    ),
    "data_analyst_zh": InterviewConfig(
        job_title="数据分析师",
        language="zh",
        persona="friendly",
        interviewer_role="hiring_manager",
        difficulty="junior",
        duration_min=15,
        resume_text=(
            "李晴，2 年数据分析经验。\n"
            "用户流失预测：用 SQL 构建特征，XGBoost 建模，AUC 0.82；推动运营做定向挽留，月流失率下降 1.5 个百分点。\n"
            "A/B 测试平台：负责实验指标体系和显著性检验报告。\n"
            "技能：SQL, Python, Pandas, Tableau, 假设检验"
        ),
        job_description="电商数据分析师。要求：熟练 SQL 和 Python；理解 A/B 测试；能把分析结论转化为业务建议。",
    ),
    "frontend_en": InterviewConfig(
        job_title="Frontend Engineer",
        language="en",
        persona="pressure",
        interviewer_role="tech_lead",
        difficulty="senior",
        duration_min=15,
        resume_text=(
            "Sam Rivera, 6 years frontend.\n"
            "Led migration of a 400k-line dashboard from AngularJS to React + TypeScript over 9 months, "
            "incremental via module federation; cut bundle size 45% and LCP from 4.1s to 1.8s.\n"
            "Built a design system (40 components, Storybook, visual regression tests) used by 6 teams.\n"
            "Skills: TypeScript, React, Next.js, GraphQL, Webpack, Vite, Playwright"
        ),
        job_description="Senior Frontend Engineer. Own performance and architecture of a large React app; mentor engineers; strong TypeScript; testing culture.",
    ),
    "pm_en": InterviewConfig(
        job_title="Product Manager",
        language="en",
        persona="neutral",
        interviewer_role="hr",
        difficulty="intermediate",
        duration_min=15,
        resume_text=(
            "Alex Chen, 4 years PM at a fintech startup.\n"
            "Launched instant payouts for merchants: discovery with 30 merchant interviews, "
            "shipped in 3 months, adopted by 22% of merchants, +8% retention.\n"
            "Ran pricing experiment that raised conversion of the paid tier from 3.1% to 4.0%.\n"
            "Skills: discovery, roadmapping, SQL, experimentation, stakeholder management"
        ),
        job_description="Product Manager for a B2B payments product. Data-informed, strong communication, experience working with engineering and sales.",
    ),
}
