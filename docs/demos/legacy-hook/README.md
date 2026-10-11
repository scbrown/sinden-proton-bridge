# Legacy tracker hook demonstration

A disposable Git commit with the historical hook invokes the retired tracker once.
After removing that hook entry, the same commit path invokes it zero times and
finishes with clean stderr. The tracker fixture models exit 3 and never opens
an issue store. This demonstrates the hook lifecycle, not installed service behavior.

Implementation revision: `dabdb95`; historical hook revision:
`d188ba2177632f6f95004616b88683e1128fe366`. The final PR retains the same workflow
probe and adds this recording. The strengthened source assertion also rejects a
dangling hook symlink; that negative control passed separately.

[Recorded terminal output](output.txt) and [timing data](timing.txt) are retained
with the repository as a small review artifact. Playback requires downloading
both files and util-linux `scriptreplay`; inline playback is not claimed:

```sh
scriptreplay --log-out output.txt --log-timing timing.txt
```

To reproduce, run the Python block in
`.github/workflows/legacy-tracker-hook.yml` from the candidate checkout. The
workflow uses the actual historical hook bytes for its positive control and a
private temporary repository for both commits.
