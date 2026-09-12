# Git, GitHub, and Maven Commands

## Git and GitHub

### Check Git

``` bash
git --version
```

Displays the installed Git version.

### Configure Git

``` bash
git config --global user.name "Your Name"
git config --global user.email "your-email@example.com"
```

Sets the name and email attached to commits.

### Initialize a repository

``` bash
git init
```

Creates a Git repository in the current directory.

### Clone a repository

``` bash
git clone https://github.com/username/project.git
```

Downloads an existing GitHub repository.

### Enter a directory

``` bash
cd project
```

Moves into the project folder.

### Check status

``` bash
git status
```

Shows the current branch, modified files, deleted files, untracked
files, and staged files.

### Stage one file

``` bash
git add file
```

Adds one file to the staging area.

### Stage everything

``` bash
git add .
```

Stages all changes in the current directory.

### Commit

``` bash
git commit -m "Message"
```

Creates a commit from staged changes.

### View history

``` bash
git log
git log --oneline
```

Displays detailed or compact commit history.

### View changes

``` bash
git diff
git diff --staged
```

Shows unstaged or staged changes.

### Unstage a file

``` bash
git restore --staged file
```

Removes a file from staging without deleting its changes.

### Discard file changes

``` bash
git restore file
```

Restores a file to its last committed version. Uncommitted changes may
be lost.

### Delete a file

``` bash
git rm file
```

Deletes and stages the file deletion.

### Restore a deleted file

``` bash
git restore file
```

Restores an uncommitted deletion.

``` bash
git restore --source=HEAD~1 file
```

Restores the file from the previous commit.

### Rename a file

``` bash
git mv old-name new-name
```

Renames and stages a file.

### Amend the last commit

``` bash
git commit --amend -m "Correct message"
```

Changes the latest commit message.

``` bash
git add file
git commit --amend --no-edit
```

Adds new staged changes to the previous commit.

### Branch commands

``` bash
git branch
```

Lists local branches.

``` bash
git branch branch-name
```

Creates a branch.

``` bash
git switch branch-name
```

Switches branches.

``` bash
git switch -c branch-name
```

Creates and switches to a branch.

``` bash
git branch -d branch-name
```

Deletes a merged branch.

### Remote commands

``` bash
git remote -v
```

Shows connected remote repositories.

``` bash
git remote add origin URL
```

Adds a remote repository.

``` bash
git remote set-url origin URL
```

Changes a remote URL.

``` bash
git remote remove origin
```

Removes a remote.

### Push

``` bash
git push -u origin main
```

Uploads the main branch and sets its upstream.

``` bash
git push -u origin branch-name
```

Uploads a feature branch.

``` bash
git push
```

Uploads later commits to the upstream branch.

### Fetch and pull

``` bash
git fetch origin
```

Downloads remote information without merging.

``` bash
git pull
```

Fetches and merges remote changes.

### Merge

``` bash
git switch main
git merge branch-name
```

Merges the branch into main.

``` bash
git merge --abort
```

Cancels an unfinished merge.

### Resolve a conflict

``` bash
git status
```

Finds conflicted files. Manually remove conflict markers, then run:

``` bash
git add conflicted-file
git commit -m "Resolve merge conflict"
```

### .gitignore

``` bash
touch .gitignore
```

Creates a file listing items Git should ignore.

Example:

``` gitignore
target/
*.class
.env
.idea/
.DS_Store
```

### Reset

``` bash
git reset --soft HEAD~1
```

Removes the last commit but keeps changes staged.

``` bash
git reset HEAD~1
```

Removes the last commit and unstages changes.

``` bash
git reset --hard HEAD~1
```

Removes the last commit and discards changes. Use carefully.

### Revert

``` bash
git revert commit-id
```

Creates a new commit that reverses an earlier commit. Safer for shared
branches.

### Stash

``` bash
git stash
git stash list
git stash pop
git stash apply
git stash drop
```

Temporarily saves, lists, restores, applies, or deletes uncommitted
changes.

### Tags

``` bash
git tag v1.0
git tag
git push origin v1.0
```

Creates, lists, and pushes a version tag.

## Complete Git workflow

``` bash
git clone URL
cd project
git status
git switch -c feature-name
git add .
git commit -m "Add feature"
git push -u origin feature-name
```

## Maven

Maven uses `pom.xml` to define project information, dependencies,
plugins, Java version, and packaging.

### Check Maven

``` bash
mvn -version
```

Displays Maven and Java information.

### Check Java

``` bash
java -version
javac -version
```

Displays the Java runtime and compiler versions.

### Validate

``` bash
mvn validate
```

Checks whether the project and POM are valid.

### Clean

``` bash
mvn clean
```

Deletes the `target/` directory.

### Compile

``` bash
mvn compile
```

Compiles main Java source files.

### Test

``` bash
mvn test
```

Compiles and runs tests.

### Package

``` bash
mvn package
```

Creates a distributable JAR or WAR file.

### Install

``` bash
mvn install
```

Installs the artifact into the local Maven repository, usually
`~/.m2/repository`.

### Deploy

``` bash
mvn deploy
```

Uploads the artifact to a configured remote Maven repository.

### Clean and package

``` bash
mvn clean package
```

Deletes old build output and creates a fresh package.

For the AI-OLMS project, this creates:

``` text
target/AI-OLMS.war
```

### Skip tests

``` bash
mvn package -DskipTests
```

Packages the project without executing tests.

``` bash
mvn package -Dmaven.test.skip=true
```

Skips test compilation and execution.

### Dependency tree

``` bash
mvn dependency:tree
```

Displays project dependencies and their relationships.

### Effective POM

``` bash
mvn help:effective-pom
```

Displays the final POM after defaults and inheritance are applied.

### Debug mode

``` bash
mvn -X package
```

Displays detailed debugging information.

### Use another POM

``` bash
mvn -f another-pom.xml package
```

Builds using a specified POM file.

## Important POM settings

### WAR packaging

``` xml
<packaging>war</packaging>
```

Tells Maven to create a WAR file.

### Java 17

``` xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

Compiles the project for Java 17.

### WAR filename

``` xml
<build>
    <finalName>AI-OLMS</finalName>
</build>
```

Creates `target/AI-OLMS.war`.

## Maven lifecycle

``` text
validate → compile → test → package → install → deploy
```

-   `validate`: checks the project
-   `compile`: compiles source code
-   `test`: runs tests
-   `package`: creates JAR/WAR
-   `install`: installs locally
-   `deploy`: uploads remotely

## Most important differences

\`\`\`text git add = stage changes git commit = save changes locally git
push = upload commits to GitHub

mvn compile = compile Java code mvn package = create JAR/WAR mvn install
= install artifact locally
