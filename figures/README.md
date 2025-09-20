# Figures Directory

The PNG images referenced in the documentation are generated on demand by the
analysis scripts. To keep the repository text-only (as requested for CDC PR
submissions), the rendered figures are ignored by git and are not committed.

Run the following commands after setting up the environment to recreate the
visuals locally:

```bash
python analysis/ps_overview.py        # baseline exploratory charts (radius vs. Teff, period vs. multiplicity, distance)
python analysis/habitable_priority.py # habitable scoring scatter/bars/radar
```

Each script will populate this folder with the corresponding PNG exports (for
example `figures/habitability/temp_radius_priority.png`). Attach those generated
files manually when preparing slide decks or DevPost submissions.
