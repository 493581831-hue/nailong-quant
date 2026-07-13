# Nailong Capital Quantitative Research Platform

面向 A 股研究、公式 Alpha 发现、回测、组合归因与交易验证的机构级 Streamlit 工作台。

## 本次重构

- 信息架构从“功能堆叠”改为“发现信号 → 验证策略 → 组合归因 → 纪律执行”
- 每个模块统一为“决策目标 → 四步流程 → 参数输入 → 结果审阅”
- 视觉系统采用全球投行式编辑排版：首页恢复鲜明的奶龙黄主题与大型动态主角，研究功能页保留高对比度的机构级内容区
- Plotly 图表、指标卡、表格、表单、状态提示和侧边导航使用同一机构化设计语言
- 首页采用动态信号环、流动光影与曲线路径；内容模块改为无边框能力流，取消传统卡片宫格
- 功能页使用弧形场景页首、胶囊流程带、下划线式输入和圆角数据表面，弱化方框感
- 首页与全部十个功能页面均配置奶龙角色/贴图，其中 Alpha² 实验室使用独立“思考奶龙”，数据源中心使用“数据侦察奶龙”
- 新增三套原创 3D 奶龙模型：动态信号队长、五角色量化研究小队、多资产 Alpha 模型奶龙；首页使用大型动态角色，所有功能页均增加五只值守奶龙
- 奶龙动画包含漂浮、呼吸、光环旋转、研究小队巡航与模型球悬浮，并为“减少动态效果”系统设置提供无动画降级
- 增加 Alpha² 单资产适配复现：量纲合法公式库、20日远期目标、时序 IC/Rank IC、低相关选择、组合信号与样本外回测
- 增加 Alpha2 多资产防守引擎：固定八类 ETF、月频双动量、长期趋势过滤、波动率预算、现金缓冲与 2021 年后独立样本外审计
- 增加 QuantDinger 启发的轻量研究工作台：持久关注池、策略快照与执行审计
- 保留策略回测、组合回测、自动选股、模拟盘、自动交易与数据导出；所有可见回测只使用真实历史数据
- 信号筛选从 5,000+ 只全市场盲扫收缩为动态精选 500 池：主路径载入最新中证 A500（000510）成分股，断网时降级为沪深300与中证500组合备用池
- 自动交易默认载入 BaoStock 沪深全市场 A 股，支持 ST/退市整理过滤、分片轮转扫描与并发行情获取，同时保留选股结果和自定义股票池
- 接入 efinance 同源东方财富直连与腾讯兼容链路，保留实际来源审计，不再用模拟行情自动降级
- 新增数据源与 Skill 中心：实时探测 efinance/腾讯、交叉验证收盘价，并链接 China Stock Analysis Skill 与官方数据项目
- 增加窄屏响应式规则，不改变原有研究和交易逻辑

## 运行

```bash
pip install -r requirements.txt
streamlit run app.py
```

如果命令行没有注册 `streamlit`，可使用：

```bash
python3 -m streamlit run app.py
```

只在本机 8502 端口运行（不创建云端隧道）：

```bash
python3 -m streamlit run app.py --server.address 127.0.0.1 --server.port 8502
```

## 关键文件

- `app.py`：页面结构、交互与业务入口
- `institutional.css`：最终视觉系统覆盖层
- `quant_a/visualization/__init__.py`：机构化图表主题
- `quant_a/alpha2_single/__init__.py`：Alpha² 单资产公式发现与回测适配
- `quant_a/alpha2_multi/__init__.py`：Alpha2 多资产真实行情、风险预算与回测引擎
- `quant_a/research_workspace/__init__.py`：关注池、快照与审计留痕
- `quant_a/data_fetcher/__init__.py`：平台历史源与 efinance 标准化适配
- `assets/generated_nailong/`：原创奶龙信号队长、量化小队与 Alpha 模型透明角色资产
- `.streamlit/config.toml`：Streamlit 基础主题配置

## 风险提示

平台仅用于研究与流程验证，不构成投资建议。历史回测表现不代表未来收益。Alpha² 页面是论文方法的单资产时序适配，不是论文原始横截面 DRL+MCTS 基准的精确复刻。
