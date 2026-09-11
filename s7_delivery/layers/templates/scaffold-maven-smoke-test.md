---
id: scaffold-maven-smoke-test
layer: template
title: New-application scaffold — Maven build smoke test
stage: intake
summary: One passing test committed with the new-application Maven scaffold, so the repository's first CI run is genuinely green and surefire writes a report. It proves the toolchain, nothing else — which is exactly what makes a later red run attributable to the published test skeletons rather than to a broken build.
---
package smoke;

import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

/**
 * Committed by S7 when this repository was provisioned. It asserts nothing
 * about the application — its only job is to make the build produce a real
 * surefire report from the first commit, so that a later failing run is
 * attributable to the code under test and not to a project that never
 * compiled. Delete it once real tests exist.
 */
class BuildSmokeTest {

    @Test
    void buildToolchainRunsTests() {
        assertTrue(true, "the Maven toolchain compiles and runs tests");
    }
}
