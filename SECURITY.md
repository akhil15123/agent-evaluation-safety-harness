# Security policy

Please report vulnerabilities privately through GitHub's **Report a vulnerability** flow rather than opening a public issue.

Do not place real secrets, customer data, or production traces in evaluation fixtures. Agent Harness redacts evidence matched by its built-in secret detectors, but endpoint-provided trace fields are controlled by the integrator and must be scrubbed before they are returned.

The built-in scanners are defense-in-depth examples, not a guarantee of safety. High-impact tools should enforce authorization and validation outside the model and harness.
