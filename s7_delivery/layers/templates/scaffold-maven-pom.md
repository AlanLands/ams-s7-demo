---
id: scaffold-maven-pom
layer: template
title: New-application scaffold — Maven pom.xml
stage: intake
summary: The minimal buildable Maven project S7 commits alongside the CI workflow when it creates a brand-new Java repository that has no build file yet. Without it `mvn -B test` fails before any test runs, so CI is red for a reason that has nothing to do with the published red baseline. Deliberately framework-free — JUnit 5, surefire and jacoco only; the stories add their own starters through the one manifest hunk the git workflow allows.
variables: artifact_id
---
<?xml version="1.0" encoding="UTF-8"?>
<!--
  Created by S7 when this repository was provisioned, so that `mvn test`
  runs from the first commit and CI evidence means something. It carries no
  application framework on purpose: a story that needs one adds it here in
  its own single, named commit (see .s7/shared/git-workflow.md).
-->
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <groupId>com.mapleweb</groupId>
  <artifactId>{{artifact_id}}</artifactId>
  <version>0.1.0-SNAPSHOT</version>
  <packaging>jar</packaging>
  <name>{{artifact_id}}</name>

  <properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <maven.compiler.release>21</maven.compiler.release>
    <junit.version>5.10.2</junit.version>
    <surefire.version>3.2.5</surefire.version>
    <jacoco.version>0.8.12</jacoco.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <version>${junit.version}</version>
      <scope>test</scope>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>${surefire.version}</version>
      </plugin>
      <!-- Binds the coverage agent so target/site/jacoco/jacoco.xml exists;
           the S7 CI workflow reads its report-root LINE counter. Without
           this, coverage is reported as unset for the life of the repo. -->
      <plugin>
        <groupId>org.jacoco</groupId>
        <artifactId>jacoco-maven-plugin</artifactId>
        <version>${jacoco.version}</version>
        <executions>
          <execution>
            <id>prepare-agent</id>
            <goals><goal>prepare-agent</goal></goals>
          </execution>
          <execution>
            <id>report</id>
            <phase>test</phase>
            <goals><goal>report</goal></goals>
          </execution>
        </executions>
      </plugin>
    </plugins>
  </build>
</project>
