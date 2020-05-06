# SignalfxUploader

Taurus plugin to stream results to SignalFX API

## Installation

```bash
git clone https://github.com/doctornkz/signalfxUploader.git
cd signalfxUploader/
pip install .
```

## Example of configuration file

```ini
execution:
- executor: pbench
  concurrency: 100
  ramp-up: 1m
  hold-for: 10m
  iterations: 5
  throughput: 10
  scenario: simple_usage

scenarios:
  simple_usage:  
    default-address: https://example.com:443/
    requests:
    - /

reporting:
  - module: signalfx

modules:
  console:
    disable: true
  signalfx:
    address: https://<REALM>.signalfx.com  # reporting service address
    data-address: https://ingest.eu0.signalfx.com/v2/datapoint   # data service address
    dashboard-url: https://<REALM>.signalfx.com/#/dashboard/<DASHBOARD_ID> # your dashboard for rendering results 
    project: test_project 
    browser-open: start  # auto-open the report in browser, 
                         # can be "start", "end", "both", "none"
    send-interval: 5s   # send data each n-th second
    timeout: 5s  # connect and request timeout for BlazeMeter API
    custom_tags:
      sf_hires: '1' # option to use high resolution SFX metrics
    token: <SIGNALFX_TOKEN>
```

## Starting

```bash
$ bzt load.yaml
19:11:53 INFO: Taurus CLI Tool v1.13.9
19:11:53 INFO: Starting with configs: ['load.yaml']
19:11:53 INFO: Configuring...
19:11:53 INFO: Artifacts dir: /tmp/bzt
19:11:53 INFO: Preparing...
19:11:53 WARNING: PBench check stderr: Usage:
        phantom run <conffile> [args]
        phantom check <conffile> [args]
        phantom syntax [modules]

19:11:53 INFO: Using stock version for pbench tool
19:11:53 INFO: Generating payload file: /tmp/bzt/pbench-3.src
19:11:53 INFO: Generating request schedule file: /tmp/bzt/pbench-3.sched
100% [========================================================================================================================================================] Time: 0:00:00
19:11:53 INFO: Done generating schedule file
19:11:54 INFO: Starting...
19:11:54 INFO: Waiting for results...
19:11:54 INFO: Started data feeding: https://***********.signalfx.com/#/dashboard/************?startTime=-15m&endTime=Now&sources%5B%5D=project:test_project&sources%5B%5D=uuid:6594ca92-e9bc-41ac-aa78-e31e55f1da1c&density=4
19:11:54 WARNING: There is newer version of Taurus 1.14.2 available, consider upgrading. What's new: http://gettaurus.org/docs/Changelog/
19:12:00 WARNING: Please wait for graceful shutdown...
19:12:00 INFO: Shutting down...
19:12:00 INFO: Post-processing...
19:12:00 INFO: Test duration: 0:00:06
19:12:00 INFO: Samples count: 5, 0.00% failures
19:12:00 INFO: Average times: total 0.729, latency 0.195, connect 0.397
19:12:00 INFO: Percentiles:
┌───────────────┬───────────────┐
│ Percentile, % │ Resp. Time, s │
├───────────────┼───────────────┤
│           0.0 │         0.644 │
│          50.0 │         0.692 │
│          90.0 │         0.938 │
│          95.0 │         0.938 │
│          99.0 │         0.938 │
│          99.9 │         0.938 │
│         100.0 │         0.938 │
└───────────────┴───────────────┘
19:12:00 INFO: Request label stats:
┌───────┬────────┬─────────┬────────┬───────┐
│ label │ status │    succ │ avg_rt │ error │
├───────┼────────┼─────────┼────────┼───────┤
│ /     │   OK   │ 100.00% │  0.729 │       │
└───────┴────────┴─────────┴────────┴───────┘
19:12:00 INFO: Sending remaining KPI data to server...
19:12:01 INFO: Report link: https://***********.signalfx.com/#/dashboard/************?startTime=-15m&endTime=Now&sources%5B%5D=project:test_project&sources%5B%5D=uuid:6594ca92-e9bc-41ac-aa78-e31e55f1da1c&density=4
19:12:01 INFO: Artifacts dir: /tmp/bzt
19:12:01 INFO: Done performing with code: 0
```

## Dashboard example

![Dashboard](/promo/dashboard_example.png)
