# Setting up a new study (or species)

Every study is just a new `config.json` - no code to write.

1. Prepare `preseg.csv` and `database.csv` (see [Your first study](first-study.md), step 1).
2. Write the config, either
   - with the **Config Editor**: *New* → browse the CSVs → **Show CSV columns...** for the key columns → Images tab
     quick-add → *Save*; or
   - by copying a file from [`examples/config/`](../examples/config) and editing it against the
     [Config reference](../docs/config-reference.md).
3. In the module: **Select .json file** → **Initialize Study**.

Config browsing remembers the folder of the config you used last, so your own configs are one click away next time.
