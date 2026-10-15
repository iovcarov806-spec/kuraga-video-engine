# Mascot assets (not shipped)

The 19 approved КУРАГА illustrations are private and are **not** committed to
this repository (everything else in this folder is gitignored).

To use the real art, copy the files here (or set `KURAGA_ASSETS_DIR`):

```
01_welcome_study.jpg      08_stairwell_variant.jpg   15_error_alleyway_500.jpg
02_office_desk.jpg        09_tokens_depleted.jpg     16_error_bench_404.jpg
03_library_sourcing.jpg   10_bbq_celebration.jpg     17_vip_club.jpg
04_code_generation.jpg    11_paywall_main.jpg        18_paywall_90s_mugging.jpg
05_work_ready_positive.jpg 12_paywall_subway.jpg     19_maintenance_worker.png
06_armchair_noodles.jpg   13_payment_terminal.jpg
07_padik_break.jpg        14_error_iv_drip.jpg
```

Resolution per stem: `manifest.json` (`{"<stem>": "<file>"}`) > exact
`<stem>.jpg|.jpeg|.png|.webp` > any image starting with the stem's `NN_`
number. Check with `python -m kuraga_video_engine assets`.

Missing stems never break a render: the engine draws a generated КУРАГА
placeholder scene (labeled with the stem) and prints a warning.
