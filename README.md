# 铸造炉次成分纠偏

面向炉前质检的本地工作台。内置业务样例覆盖铸造炉前成分残差检测、称料纠偏与炉次放行。样例采用确定性构造，适合复现实验和核查边界行为。

## 启动

```sh
docker compose up --build -d
```

打开 `http://127.0.0.1:18211/` 查看炉次纠偏单。左侧六个入口可展开运行证据。调整「炉次纠偏限量」，点击「重算纠偏」比较处置结果。结束后执行 `docker compose down --remove-orphans`。

## 独立业务模块

- 化验记录 `ladle_assays`
- 料批追踪 `material_grade`
- 残差识别 `chemistry_residuals`
- 风险分级 `alloy_tolerance`
- 称料纠偏 `charge_correction`
- 炉前交割 `heat_release`

## 查看运行结果

- `GET /api/overview` 返回默认运行及其指纹。
- `POST /api/scenario` 接收 `{"capacity": 3}`。入口接受 1–100 的整数，应用样例时使用该业务额度。
- `GET /api/stages/heat_release` 查看该环节的独立证据，支持 `?capacity=3`。

```sh
docker compose exec -T app python -m foundrychem.delivery evaluate --capacity 3
docker compose exec -T app pytest -q
```

数据和模型约定见 [业务契约](docs/SPEC.md)。模块、例外规则与验证入口见 [业务深度](docs/DEPTH.md)。
