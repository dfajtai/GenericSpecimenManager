# Your first study

A step-by-step walk from raw files to your first batch export. Read the
[repository README](../README.md) first if you want the idea behind it.

## 1. Prepare the two CSVs

A study needs two tables that share the same **key columns** (the columns that identify one specimen, e.g. `ID`, or
`ID` + `measurement`):

- **`preseg.csv`** - one row per specimen, with the key columns and one column per image holding its file path
  (or the part of the path a pattern needs), e.g.:

  ```
  ID,measurement,background,mask
  P001,baseline,P001/baseline/ct.nii.gz,P001/baseline/mask.nii.gz
  ```

- **`database.csv`** - one row per specimen, with the same key columns plus anything you want to record
  (a `comment` column, measured values, a group column such as `batch`, ...). You do **not** have to add a status
  column - the module offers to create it.

The key values must match, row for row, in both files. (Automating this step is on the [roadmap](../docs/roadmap.md).)

## 2. Install the module

See *Quick start* in the [repository README](../README.md): add
`<clone>/GenericSpecimenManager/GenericSpecimenManager` as an additional module path in Slicer and restart it.

## 3. Create the config

1. Open *Segmentation → Generic Specimen Manager* and press **Config Editor...** → *Open clean Config Editor*
   (or start from a file in [`examples/config/`](../examples/config), e.g. `example_minimal.json`, and adjust it).
2. **General** tab: pick the preseg CSV and the database CSV, use **Show CSV columns...** to see the column names, set
   the **Key columns**, and choose which **Table columns** the specimen table should show.
3. **Images** tab: add one row per image - *Quick add from preseg columns...* offers the preseg columns in a popup - and mark one as the `background`.
4. **Segmentation** tab: enable it, choose the reference image, and list your segments.
5. Optionally set up **Markups**, the **Workspace**, and **Batch export** (you can come back to this later).
6. **Save config**. Say *yes* when it asks to reload the config in the module.

Every field has a tooltip, and the Config Editor's **Help** button opens a searchable cheat sheet.

## 4. Initialize and work

1. Press **Initialize Study**. If the config expects columns that `database.csv` lacks (the status column, factor
   columns), the module offers to create them and writes them to the file straight away.
2. Select a specimen row in the **Specimen browser**, press **Load selected specimen**.
3. Segment and place markups as usual. Press **Save progress for active specimen** or `Ctrl+S` when you want to keep
   the work.
4. **Close active specimen**. Choose *Yes, mark to review* or *Yes, mark finished* if it is ready.

Statuses: `untouched` → `in progress` (set automatically when a specimen is saved or loads from its own saved
file) → `to review` → `finished`. You can also change a status from the dropdown in the table.
Details: [The main module](../docs/main-module.md).

## 5. Export

When some specimens are *finished*, and batch export is enabled in the config, press **Batch export** (under
*Initialize Study*). It writes, in one pass and only for finished specimens, whatever you enabled: per-segment label
maps, a segment-statistics CSV and a markup summary CSV.
Details: [Batch export](../docs/batch-export.md).

## When something goes wrong

- **The path field is yellow or red** - the config path is a folder or missing; use *Select .json file*.
- **"No specimen has the status 'finished'"** when exporting - set the status of at least one specimen to
  *finished* first.
- **Something looks off in the config** - the [Config reference](../docs/config-reference.md) lists every key.
