# ant-devices

Host inventory. Reports CPU count and SIMD features, GPUs, total memory, and whether we are running on a Jetson. Served at `/api/v1/devices` and by `arikizu status --dev`.

## What it detects

| Field          | Linux source                                | Fallback                 |
| -------------- | ------------------------------------------- | ------------------------ |
| `cpus[].cores` | `std::thread::available_parallelism()`      | 1                        |
| `cpus[].simd`  | `is_x86_feature_detected!` / `cfg aarch64`  | empty                    |
| `gpus[]`       | NVML / nvidia-smi (Weekend 4 fills this in) | empty                    |
| `total_memory_mb` | `/proc/meminfo`                          | 0                        |
| `platform`     | `std::env::consts::OS` + ARCH               | always set               |
| `is_jetson`    | `/etc/nv_tegra_release` or `/proc/device-tree/model` | false            |

The v0.1 GPU detection is a stub returning `[]`; the live `nvidia-smi` parse lands with the model manager.

## API

```rust
use ant_devices::DeviceInventory;

let inv = DeviceInventory::detect()?;
println!("{} / {} MB", inv.platform, inv.total_memory_mb);
println!("Jetson: {}", inv.is_jetson);
```

## Tests

```
cargo test -p ant-devices
```

Covers: non-empty cpus list, non-empty platform string.

## Where the output goes

- The dashboard overview page shows platform, is_jetson, CPU and GPU counts
- The HTTP `/api/v1/status` summary includes device counts
- `arikizu status --dev` prints the full inventory as JSON or a human table
