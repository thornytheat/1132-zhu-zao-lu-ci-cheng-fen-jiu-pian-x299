# 铸造炉次成分纠偏功能与验证

领域为 AI/ML / 传统ML。

## 功能模块

| 模块 | 使用者动作 | 入口 | 核心文件 | 测试 |
|---|---|---|---|---|
| M1 化验记录 | 筛除未见、修订冲突或无法复测的炉前化验 | 运行证据第 1 段 | `src/foundrychem/ladle_assays/contracts.py` `src/foundrychem/ladle_assays/analysis.py` `src/foundrychem/ladle_assays/service.py` | `tests/test_ladle_assays.py` |
| M2 料批追踪 | 核验生效证书和可用料批 | 运行证据第 2 段 | `src/foundrychem/material_grade/contracts.py` `src/foundrychem/material_grade/analysis.py` `src/foundrychem/material_grade/service.py` | `tests/test_material_grade.py` |
| M3 残差识别 | 以历史炉次拟合终检和炉前偏移 | 运行证据第 3 段 | `src/foundrychem/chemistry_residuals/contracts.py` `src/foundrychem/chemistry_residuals/analysis.py` `src/foundrychem/chemistry_residuals/service.py` | `tests/test_chemistry_residuals.py` |
| M4 风险分级 | 校准测量不确定性并拦截域外工况 | 运行证据第 4 段 | `src/foundrychem/alloy_tolerance/contracts.py` `src/foundrychem/alloy_tolerance/analysis.py` `src/foundrychem/alloy_tolerance/service.py` | `tests/test_alloy_tolerance.py` |
| M5 称料纠偏 | 基于台架步进和事先限额发放台架预留 | 运行证据第 5 段 | `src/foundrychem/charge_correction/contracts.py` `src/foundrychem/charge_correction/analysis.py` `src/foundrychem/charge_correction/service.py` | `tests/test_charge_correction.py` |
| M6 炉前交割 | 复验和终检签字，只有完整成分组允许交割 | 运行证据第 6 段 | `src/foundrychem/heat_release/contracts.py` `src/foundrychem/heat_release/analysis.py` `src/foundrychem/heat_release/service.py` | `tests/test_heat_release.py` |

## 陷阱登记

| TRAP | 输入情形 | 错误风险 | 处理 | 处理位置 | 测试 |
|---|---|---|---|---|---|
| TRAP-23 | 材料证书恰于工作日失效 | 两个证书版本同时生效 | 使用半开生效区间 | `src/foundrychem/material_grade/analysis.py` | `tests/test_material_grade.py::test_certificate_expiry_is_exclusive` |
| TRAP-26 | 旧化验结果晚到 | 历史报化验覆盖最近数据 | 仅采用最高有效修订，冻结同修订冲突 | `src/foundrychem/ladle_assays/analysis.py` | `tests/test_ladle_assays.py::test_old_revision_cannot_override_current_assay` |
| TRAP-31 | 离工艺界限远导致极端风险值 | sigmoid 指数上溢 | 负绝对值指数求值 | `src/foundrychem/alloy_tolerance/analysis.py` | `tests/test_alloy_tolerance.py::test_very_large_margin_has_finite_risk` |
| TRAP-32 | 恒定设备条件和大偏移读数 | 尺度退化导致数值不稳定 | 中位绝对离差加正数尺度地板 | `src/foundrychem/chemistry_residuals/analysis.py` | `tests/test_chemistry_residuals.py::test_flat_and_large_offset_changes_keep_robust_width` |
| TRAP-42 | 旧炉次补录的终检样本 | 按炉次日漏掉真实可见时点 | 炉次日和发布时间均早于使用日 | `src/foundrychem/chemistry_residuals/analysis.py` | `tests/test_chemistry_residuals.py::test_late_master_assay_is_not_used_in_residual_calibration` |
| TRAP-43 | 没有留出验证数据 | 超差率除零 | 保留未知状态且禁自动审批 | `src/foundrychem/alloy_tolerance/analysis.py` | `tests/test_alloy_tolerance.py::test_empty_holdout_yields_undefined_exceedance` |
| TRAP-44 | 偏离历史温区但化验的点值正常 | 忽视工况支持，误判合格 | 联用预测区间与历史距离做挂起 | `src/foundrychem/alloy_tolerance/analysis.py` | `tests/test_alloy_tolerance.py::test_nominal_estimate_does_not_release_out_of_support_heat` |
| TRAP-53 | 混入极端炉次的批量复核 | 其他炉次改变已有炉号的参考尺度 | 以固定训练期稳健尺度逐炉复核 | `src/foundrychem/chemistry_residuals/analysis.py` | `tests/test_chemistry_residuals.py::test_score_of_one_heat_independent_of_batched_order` |
