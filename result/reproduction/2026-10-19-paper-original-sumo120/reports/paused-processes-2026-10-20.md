# User-requested pause, 2026-10-20

## Superseding update: memory release requested

The user subsequently requested メモリを解放したい. All 29 PIDs listed below
were revalidated against their commands, parent relationships and stopped states,
then terminated with SIGKILL without resuming the queues. In-memory progress is
no longer available. Do not SIGCONT these PIDs on a later resume request.
Completed result files were preserved; no files were deleted. Unfinished formal
cases and the unfinished trace diagnostic require a fresh run. Existing partial
trace output is not a successfully completed 60-second diagnostic. The goal stays
paused until the user asks to resume.

## Previous paused state (historical)

User explicitly requested 一時停止. All experiment controllers, eight formal
Python/SUMO pairs, and the active diagnostic Python/SUMO pair were sent SIGSTOP.
All listed processes were verified in T/TN/Ts/TNs state immediately afterward.
No simulations were terminated; live state remains in memory, not a durable
checkpoint. Reboot or process termination loses unfinished in-memory progress.

Stopped PIDs:
2767 33733 38265 38519 38520 38522 38524 38526 38528 38530 38532
38533 38535 38536 38538 38539 38540 38541 38542
38592 38593 38594 38595 38596 38597 38598 38599 91669 91828

Controllers: 2767 queued SUMO 1.17 diagnostic; 33733 finalizer; 38265 paper queue.
Diagnostic: 91669 Python, 91828 SUMO, output diagnostics/sumo-trace-1.20.0-8jtwccec.
Formal paper children: 38519..38532 are queue wrappers, 38533..38542 Python,
38592..38599 SUMO (only explicitly listed IDs, not all integers in ranges).

The task's caffeinate process 38516 was terminated to release its sleep
prevention assertion. Sleep children of the stopped controllers may finish;
their stopped parents cannot advance the queues.

Resume only on explicit user request. Before SIGCONT, revalidate each PID's
command/parent identity and stopped state; never blindly signal reused PIDs.
Restore sleep prevention only if resuming computation. Existing completed
results and Google Drive were not modified.
