# Build

每个脚本都有独立的配置构建入口。打开下面对应的 Actions 页面，点击 **Run workflow**，选择 `main` 分支，再选择 KernelSU 类型和功能开关即可构建。

| 配置 | 构建入口 |
| --- | --- |
| 一加 15 金标 | [Run workflow](https://github.com/zaud77/k6r9m2p7v4x8/actions/workflows/fastbuild_6.12.23_oneplus_15_hmbird_gold.yml) |
| 一加 15 紫标 | [Run workflow](https://github.com/zaud77/k6r9m2p7v4x8/actions/workflows/fastbuild_6.12.23_oneplus_15_hmbird_purple.yml) |
| 一加 15T 金标 | [Run workflow](https://github.com/zaud77/k6r9m2p7v4x8/actions/workflows/fastbuild_6.12.38_oneplus_15t_hmbird_gold.yml) |
| 一加 15T 紫标 | [Run workflow](https://github.com/zaud77/k6r9m2p7v4x8/actions/workflows/fastbuild_6.12.38_oneplus_15t_hmbird_purple.yml) |
| Ace 6T 金标 | [Run workflow](https://github.com/zaud77/k6r9m2p7v4x8/actions/workflows/fastbuild_6.12.38_oneplus_ace6t_hmbird_gold.yml) |
| Ace 6T 紫标 | [Run workflow](https://github.com/zaud77/k6r9m2p7v4x8/actions/workflows/fastbuild_6.12.38_oneplus_ace6t_hmbird_purple.yml) |
| OPPO Find X9 金标 | [Run workflow](https://github.com/zaud77/k6r9m2p7v4x8/actions/workflows/fastbuild_6.12.23_mtk_hmbird_gold.yml) |
| OPPO Find X9 紫标 | [Run workflow](https://github.com/zaud77/k6r9m2p7v4x8/actions/workflows/fastbuild_6.12.23_mtk_hmbird_purple.yml) |
| OnePlus Pad 3 Pro 金标 | [Run workflow](https://github.com/zaud77/k6r9m2p7v4x8/actions/workflows/fastbuild_6.12.58_hmbird_gold.yml) |
| Ace 6 Ultra 金标 | [Run workflow](https://github.com/zaud77/k6r9m2p7v4x8/actions/workflows/fastbuild_6.12.58_mtk_hmbird_gold.yml) |

`sukisu` 使用 SukiSU Ultra 官方源码，`bakasu` 使用 BakaSU 源码。NoMount 与 SUSFS 只能二选一。序列号留空时使用默认自用配置。

本仓库仅保留配置与入口；构建步骤及依赖从固定的只读输入加载，全部构建在本仓库运行。
