# drsdrBench

`drsdrBench` is a test of agentic AI's ability to solve [DrSDR](https://github.com/DrSDR)'s signal decoding challenges.

## Contents

The agentic harness used in this benchmark is **OpenCode**. Currently includes 13 communications signal decoding tasks.
For message decoding, score is 1 - normalized levenshtein distance between groundtruth and decoded message.
For image decoding, score is the cosine similarity between the analog image and the groundtruth image. As long as the score is greater than 0.9, the agent is considered to have passed

## Results

### drsdrBench v0.1

Evaluation Date: 13 April 2026

<table>
  <thead>
    <tr>
      <th rowspan=2>model</th>
      <th rowspan=2>success rate</th>
      <th colspan=4, style="text-align: center; vertical-align: middle;">decode image</th>
      <th colspan=9, style="text-align: center; vertical-align: middle;">decode message</th>
    </tr>
    <tr>
      <th>AM</th>
      <th>FFT</th>
      <th>FM</th>
      <th>ofdm</th>
      <th>ofdm</th>
      <th>ofdm2</th>
      <th>QPSK</th>
      <th>FSK</th>
      <th>ofdm-audio</th>
      <th>LFMchirp</th>
      <th>ofdm-hard</th>
      <th>lora</th>
      <th>chirp</th>
    </tr>
  </thead>
  <tbody>
    <tr><td>claude-opus-4.6</td><td>13/13</td><td>✅</td><td>✅</td><td>✅</td><td>✅</td><td>✅</td><td>✅</td><td>✅</td><td>✅</td><td>✅</td><td>✅</td><td>✅</td><td>✅</td><td>✅</td></tr>
    <tr><td>gemini3.1-pro-preview</td><td>13/13</td><td>✅</td><td>✅</td><td>✅</td><td>✅</td><td>✅</td><td>✅</td><td>✅</td><td>✅</td><td>✅</td><td>✅</td><td>✅</td><td>✅</td><td>✅</td></tr>
    <tr><td>glm-5.1</td><td>13/13</td><td>✅</td><td>✅</td><td>✅</td><td>✅</td><td>✅</td><td>✅</td><td>✅</td><td>✅</td><td>✅</td><td>✅</td><td>✅</td><td>✅</td><td>✅</td></tr>
    <tr><td>gpt-5.3-codex</td><td>11/13</td><td>x</td><td>x</td><td>✅</td><td>✅</td><td>✅</td><td>✅</td><td>✅</td><td>✅</td><td>✅</td><td>✅</td><td>✅</td><td>✅</td><td>✅</td></tr>
    <tr><td>glm5</td><td>10/13</td><td>✅</td><td>x</td><td>✅</td><td>✅</td><td>x</td><td>✅</td><td>✅</td><td>✅</td><td>✅</td><td>✅</td><td>x</td><td>✅</td><td>✅</td></tr>
    <tr><td>mimo-v2-pro</td><td>9/13</td><td>✅</td><td>✅</td><td>x</td><td>✅</td><td>x</td><td>x</td><td>✅</td><td>✅</td><td>✅</td><td>✅</td><td>x</td><td>✅</td><td>✅</td></tr>
    <tr><td>kimi2.5</td><td>8/13</td><td>✅</td><td>✅</td><td>✅</td><td>x</td><td>x</td><td>x</td><td>✅</td><td>✅</td><td>x</td><td>✅</td><td>x</td><td>✅</td><td>✅</td></tr>
    <tr><td>devstral-2512</td><td>5/13</td><td>✅</td><td>✅</td><td>✅</td><td>✅</td><td>x</td><td>x</td><td>x</td><td>✅</td><td>x</td><td>✅</td><td>x</td><td>x</td><td>x</td></tr>
    <tr><td>qwen3.5_397B_A17B</td><td>5/13</td><td>✅</td><td>x</td><td>✅</td><td>x</td><td>x</td><td>x</td><td>x</td><td>✅</td><td>x</td><td>✅</td><td>x</td><td>✅</td><td>✅</td></tr>
    <tr><td>gemma-4-26b-a4b</td><td>4/13</td><td>x</td><td>✅</td><td>✅</td><td>✅</td><td>x</td><td>x</td><td>x</td><td>✅</td><td>x</td><td>x</td><td>x</td><td>x</td><td>✅</td></tr>
    <tr><td>gpt-5.4</td><td>4/13</td><td>x</td><td>x</td><td>✅</td><td>x</td><td>x</td><td>x</td><td>x</td><td>✅</td><td>✅</td><td>x</td><td>x</td><td>✅</td><td>✅</td></tr>
    <tr><td>minimax2.7</td><td>4/13</td><td>x</td><td>x</td><td>✅</td><td>x</td><td>x</td><td>x</td><td>x</td><td>✅</td><td>x</td><td>✅</td><td>x</td><td>✅</td><td>✅</td></tr>
    <tr><td>gemma-4-31b</td><td>3/13</td><td>x</td><td>x</td><td>✅</td><td>✅</td><td>x</td><td>x</td><td>x</td><td>✅</td><td>x</td><td>x</td><td>x</td><td>✅</td><td>x</td></tr>
    <tr><td>mimo-v2-flash</td><td>3/13</td><td>✅</td><td>x</td><td>✅</td><td>x</td><td>x</td><td>x</td><td>x</td><td>✅</td><td>x</td><td>x</td><td>x</td><td>x</td><td>✅</td></tr>
    <tr><td>nemotron-3-nano-30b-a3b</td><td>1/13</td><td>✅</td><td>x</td><td>x</td><td>x</td><td>x</td><td>x</td><td>x</td><td>x</td><td>x</td><td>x</td><td>x</td><td>x</td><td>x</td></tr>
    <tr><td>nemotron-3-super</td><td>1/13</td><td>x</td><td>x</td><td>x</td><td>x</td><td>x</td><td>x</td><td>x</td><td>✅</td><td>x</td><td>x</td><td>x</td><td>x</td><td>x</td></tr>
  </tbody>
</table>

## Usage

### Requirements

- Ubuntu
- docker (user in docker group)
- openrouter API key
- opencode configuration file (typically located at `~/.local/share/opencode/auth.json`)

LLM models inference are provided by `OpenRouter`.
To configure model definitions/options, edit `model_routing_config.json`.
To configure which tasks/models to run for a specific benchmark reproduction, edit `config_taskstorun.json`.

Ensure `opencode` is configured to access `OpenRouter`. Once `opencode` is configured, `~/.local/share/opencode/auth.json` should be present. Subsequent scripts may reference this path to obtain opencode configuration.

To run the full benchmark:

```bash
python3 main.py
```

To run a subset of tasks and/or models:

```bash
python3 main.py --task=decodeimg-AM --task=decodemsg-ofdm
python3 main.py --tasks=decodeimg-AM,decodemsg-ofdm --models=gpt-5.4,claude-opus-4.6
```

To evaluate the results of all models across all tasks:

```bash
python3 evaluate.py --write-csv
```

To run and evaluate a single benchmark task directly:

```bash
python3 main.py --task=<taskfolder>
python3 evaluate.py --targetdir=<taskfolder>
```

## Caveats

Since the signal processing tasks were taken from github, there is a chance that some models may have trained on them before.

## Contributions

Happy to welcome contributions in :

- correcting bugs
- new models benchmarking results
- new signal processing tasks to include

## Attribution

This benchmark is built upon the signal-decoding challenges by [DrSDR](https://github.com/DrSDR).
