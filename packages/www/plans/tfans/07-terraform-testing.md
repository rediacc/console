# Phase 2c: Terraform Provider Testing Strategy

## Testing Layers

```
Layer 1: Unit Tests (Go)                ← Fast, mock rdc CLI
  └── Test client wrapper, schema validation, state mapping

Layer 2: Acceptance Tests (Go + rdc ops) ← Real infra, real terraform apply
  └── Test full resource lifecycle against live VMs

Layer 3: Example Validation              ← terraform validate on all examples
  └── Ensure example configs are syntactically valid
```

## Layer 1: Unit Tests

Unit tests mock the `rdc` CLI and test the provider logic in isolation.

### What to Unit Test

| Component | Tests |
|-----------|-------|
| `client/rdc.go` | Command building, JSON parsing, error handling |
| `provider.go` | Configuration validation, client initialization |
| `resource_machine.go` | Schema defaults, CRUD state mapping |
| `resource_repository.go` | Schema validation, state transitions, import parsing |
| Data sources | Response mapping, attribute computation |

### Example: client/rdc_test.go

```go
package client

import (
    "context"
    "encoding/json"
    "os"
    "os/exec"
    "path/filepath"
    "testing"
)

// Helper: create a mock rdc script that outputs a known response
func createMockRdc(t *testing.T, stdout, stderr string, exitCode int) string {
    t.Helper()
    dir := t.TempDir()
    script := filepath.Join(dir, "rdc")
    content := fmt.Sprintf("#!/bin/bash\necho '%s'\necho '%s' >&2\nexit %d\n", stdout, stderr, exitCode)
    os.WriteFile(script, []byte(content), 0755)
    return script
}

func TestRdcClient_BuildsCommand(t *testing.T) {
    c := NewRdcClient("/usr/bin/rdc", "")
    // Verify --output json is included in query commands
}

func TestRdcClient_IncludesConfigFlag(t *testing.T) {
    c := NewRdcClient("/usr/bin/rdc", "production")
    // Verify --config production is included in all commands
}

func TestRdcClient_UnwrapsEnvelope(t *testing.T) {
    // Query commands return JSON envelope: {success, command, data, ...}
    // RunQuery() should extract the 'data' field
    envelope := `{"success":true,"command":"config repositories","data":{"my-app":{"repositoryGuid":"abc"}},"errors":null,"warnings":[],"metrics":{}}`
    mockBin := createMockRdc(t, envelope, "", 0)
    c := NewRdcClient(mockBin, "")

    result, err := c.RunQuery(context.Background(), "config", "repositories")
    if err != nil {
        t.Fatalf("unexpected error: %v", err)
    }

    var repos map[string]interface{}
    json.Unmarshal(result, &repos)
    if _, ok := repos["my-app"]; !ok {
        t.Error("expected 'my-app' in unwrapped data")
    }
}

func TestRdcClient_LifecycleSkipsJsonFlag(t *testing.T) {
    // RunLifecycle() should NOT include --output json
    // It only checks exit code
    mockBin := createMockRdc(t, "Starting...", "info: created", 0)
    c := NewRdcClient(mockBin, "")
    err := c.RunLifecycle(context.Background(), "repo", "create", "x", "-m", "y", "--size", "1G")
    if err != nil {
        t.Fatalf("unexpected error: %v", err)
    }
}

func TestRdcClient_HandlesEmptyOutput(t *testing.T) {
    // Query commands with empty stdout should return nil, nil
    mockBin := createMockRdc(t, "", "", 0)
    c := NewRdcClient(mockBin, "")
    result, err := c.RunQuery(context.Background(), "config", "show")
    if err != nil {
        t.Fatalf("unexpected error: %v", err)
    }
    if result != nil {
        t.Error("expected nil for empty output")
    }
}

func TestRdcClient_FailsOnNonZeroExit(t *testing.T) {
    mockBin := createMockRdc(t, "", "Error: not found", 1)
    c := NewRdcClient(mockBin, "")
    _, err := c.RunQuery(context.Background(), "config", "show")
    if err == nil {
        t.Error("expected error for non-zero exit")
    }
}
```

### Example: resource_machine_test.go (Schema Tests)

```go
package provider

import (
    "testing"
    "github.com/hashicorp/terraform-plugin-framework/resource"
    "github.com/hashicorp/terraform-plugin-testing/helper/resource"
)

func TestMachineResource_Schema(t *testing.T) {
    ctx := context.Background()
    r := NewMachineResource()

    resp := resource.SchemaResponse{}
    r.Schema(ctx, resource.SchemaRequest{}, &resp)

    // Verify required attributes
    if !resp.Schema.Attributes["name"].IsRequired() {
        t.Error("name should be required")
    }
    if !resp.Schema.Attributes["ip"].IsRequired() {
        t.Error("ip should be required")
    }

    // Verify defaults
    portAttr := resp.Schema.Attributes["port"]
    // Check default is 22

    datastoreAttr := resp.Schema.Attributes["datastore"]
    // Check default is "/mnt/rediacc"
}

func TestMachineResource_ImportId(t *testing.T) {
    // Verify import ID parsing: "machine-name" → name attribute
    tests := []struct {
        importId string
        wantName string
    }{
        {"web-1", "web-1"},
        {"my-server", "my-server"},
    }
    for _, tt := range tests {
        // Test ImportState extracts name correctly
    }
}

func TestRepositoryResource_ImportId(t *testing.T) {
    // Verify import ID parsing: "repo:machine" → name + machine
    tests := []struct {
        importId    string
        wantName    string
        wantMachine string
        wantErr     bool
    }{
        {"my-app:server-1", "my-app", "server-1", false},
        {"db:web-2", "db", "web-2", false},
        {"invalid", "", "", true},       // Missing colon
        {"a:b:c", "", "", true},         // Too many colons
    }
    for _, tt := range tests {
        // Test ImportState parsing
    }
}
```

### Running Unit Tests

```bash
cd packages/terraform/terraform-provider-rediacc
go test ./internal/client/ -v
go test ./internal/provider/ -v -run 'Test.*Schema'
go test ./internal/provider/ -v -run 'Test.*Import'
```

---

## Layer 2: Acceptance Tests

Acceptance tests run real `terraform apply/destroy` against live infrastructure.
They use `rdc ops` VMs as the target.

### Test Framework

Uses the official `terraform-plugin-testing` framework:

```go
import "github.com/hashicorp/terraform-plugin-testing/helper/resource"
```

### Environment Setup

Acceptance tests require:
1. `TF_ACC=1` environment variable
2. Running `rdc ops` VMs (rediacc11, rediacc12)
3. Machines registered and set up in rdc config
4. `rdc` binary accessible

```bash
# Setup (run once before tests)
./run.sh rdc ops up --basic --parallel
./run.sh rdc config add-machine rediacc11 --ip 192.168.111.11 --user muhammed
./run.sh rdc config add-machine rediacc12 --ip 192.168.111.12 --user muhammed
./run.sh rdc config set-ssh \
  --private-key ~/.renet/staging/.ssh/id_rsa \
  --public-key ~/.renet/staging/.ssh/id_rsa.pub
./run.sh rdc config setup-machine rediacc11
./run.sh rdc config setup-machine rediacc12

# Run acceptance tests
cd packages/terraform/terraform-provider-rediacc
TF_ACC=1 RDC_BINARY="$(pwd)/../../../run.sh rdc" go test ./... -v -timeout 30m
```

### Example: resource_machine_test.go (Acceptance)

```go
package provider

import (
    "fmt"
    "testing"
    "github.com/hashicorp/terraform-plugin-testing/helper/resource"
    "github.com/hashicorp/terraform-plugin-testing/terraform"
)

func TestAccMachineResource_basic(t *testing.T) {
    resource.Test(t, resource.TestCase{
        ProtoV6ProviderFactories: testAccProtoV6ProviderFactories,
        Steps: []resource.TestStep{
            // Step 1: Create machine
            {
                Config: `
                    resource "rediacc_machine" "test" {
                        name = "acc-test-machine"
                        ip   = "192.168.111.11"
                        user = "muhammed"
                    }
                `,
                Check: resource.ComposeAggregateTestCheckFunc(
                    resource.TestCheckResourceAttr("rediacc_machine.test", "name", "acc-test-machine"),
                    resource.TestCheckResourceAttr("rediacc_machine.test", "ip", "192.168.111.11"),
                    resource.TestCheckResourceAttr("rediacc_machine.test", "port", "22"),
                    resource.TestCheckResourceAttr("rediacc_machine.test", "datastore", "/mnt/rediacc"),
                ),
            },
            // Step 2: ImportState
            {
                ResourceName:      "rediacc_machine.test",
                ImportState:        true,
                ImportStateVerify:  true,
            },
        },
    })
}

func TestAccMachineResource_withSetup(t *testing.T) {
    resource.Test(t, resource.TestCase{
        ProtoV6ProviderFactories: testAccProtoV6ProviderFactories,
        Steps: []resource.TestStep{
            {
                Config: `
                    resource "rediacc_machine" "test_setup" {
                        name  = "acc-test-setup"
                        ip    = "192.168.111.11"
                        user  = "muhammed"
                        setup = true
                    }
                `,
                Check: resource.ComposeAggregateTestCheckFunc(
                    resource.TestCheckResourceAttr("rediacc_machine.test_setup", "setup", "true"),
                    // Verify machine health after setup
                    testCheckMachineHealthy("acc-test-setup"),
                ),
            },
        },
    })
}

func testCheckMachineHealthy(machineName string) resource.TestCheckFunc {
    return func(s *terraform.State) error {
        // Run: rdc machine health <name> --output json
        // Verify status is healthy
        return nil
    }
}
```

### Example: resource_repository_test.go (Acceptance)

```go
func TestAccRepositoryResource_lifecycle(t *testing.T) {
    resource.Test(t, resource.TestCase{
        ProtoV6ProviderFactories: testAccProtoV6ProviderFactories,
        CheckDestroy:             testAccCheckRepositoryDestroyed("acc-test-repo"),
        Steps: []resource.TestStep{
            // Step 1: Create repository
            {
                Config: `
                    resource "rediacc_repository" "test" {
                        name    = "acc-test-repo"
                        machine = "rediacc11"
                        size    = "1G"
                    }
                `,
                Check: resource.ComposeAggregateTestCheckFunc(
                    resource.TestCheckResourceAttr("rediacc_repository.test", "name", "acc-test-repo"),
                    resource.TestCheckResourceAttr("rediacc_repository.test", "machine", "rediacc11"),
                    resource.TestCheckResourceAttrSet("rediacc_repository.test", "guid"),
                    resource.TestCheckResourceAttrSet("rediacc_repository.test", "network_id"),
                ),
            },
            // Step 2: Deploy
            {
                Config: `
                    resource "rediacc_repository" "test" {
                        name    = "acc-test-repo"
                        machine = "rediacc11"
                        size    = "1G"
                        deploy  = true
                    }
                `,
                Check: resource.ComposeAggregateTestCheckFunc(
                    resource.TestCheckResourceAttr("rediacc_repository.test", "deploy", "true"),
                ),
            },
            // Step 3: Expand (online resize)
            {
                Config: `
                    resource "rediacc_repository" "test" {
                        name    = "acc-test-repo"
                        machine = "rediacc11"
                        size    = "2G"
                        deploy  = true
                    }
                `,
                Check: resource.ComposeAggregateTestCheckFunc(
                    resource.TestCheckResourceAttr("rediacc_repository.test", "size", "2G"),
                ),
            },
            // Step 4: ImportState
            {
                ResourceName:      "rediacc_repository.test",
                ImportState:        true,
                ImportStateId:      "acc-test-repo:rediacc11",
                ImportStateVerify:  true,
                ImportStateVerifyIgnore: []string{"deploy", "source_dir"},
            },
        },
    })
}

func testAccCheckRepositoryDestroyed(name string) resource.TestCheckFunc {
    return func(s *terraform.State) error {
        // Run: rdc config repositories --output json
        // Verify repo no longer exists
        return nil
    }
}

func TestAccRepositoryResource_backupBeforeDestroy(t *testing.T) {
    resource.Test(t, resource.TestCase{
        ProtoV6ProviderFactories: testAccProtoV6ProviderFactories,
        Steps: []resource.TestStep{
            {
                Config: `
                    resource "rediacc_repository" "backup_test" {
                        name    = "acc-test-backup-destroy"
                        machine = "rediacc11"
                        size    = "1G"

                        backup_before_destroy = true
                        backup_storage        = "test-storage"
                    }
                `,
            },
            // Destroy step — should backup first, then delete
            {
                Config:  " ", // empty config triggers destroy
                Destroy: true,
                Check: func(s *terraform.State) error {
                    // Verify backup exists in storage
                    return nil
                },
            },
        },
    })
}
```

### Data Source Acceptance Tests

```go
func TestAccMachinesDataSource_basic(t *testing.T) {
    resource.Test(t, resource.TestCase{
        ProtoV6ProviderFactories: testAccProtoV6ProviderFactories,
        Steps: []resource.TestStep{
            {
                Config: `data "rediacc_machines" "all" {}`,
                Check: resource.ComposeAggregateTestCheckFunc(
                    // Should have at least the test machines
                    resource.TestCheckResourceAttrSet("data.rediacc_machines.all", "machines.%"),
                ),
            },
        },
    })
}

func TestAccHealthDataSource_basic(t *testing.T) {
    resource.Test(t, resource.TestCase{
        ProtoV6ProviderFactories: testAccProtoV6ProviderFactories,
        Steps: []resource.TestStep{
            {
                Config: `
                    data "rediacc_health" "test" {
                        machine = "rediacc11"
                    }
                `,
                Check: resource.ComposeAggregateTestCheckFunc(
                    resource.TestCheckResourceAttrSet("data.rediacc_health.test", "status"),
                ),
            },
        },
    })
}
```

---

## Layer 3: Example Validation

All examples in `examples/` are validated on every CI run:

```bash
cd packages/terraform/terraform-provider-rediacc
for dir in examples/*/; do
    echo "Validating $dir..."
    cd "$dir"
    terraform init -backend=false
    terraform validate
    cd -
done
```

---

## CI Pipeline

```yaml
# .github/workflows/terraform-provider.yml
name: Terraform Provider CI

on:
  push:
    paths: ['packages/terraform/**']
  pull_request:
    paths: ['packages/terraform/**']

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-go@v5
        with:
          go-version: '1.22'
      - run: cd packages/terraform/terraform-provider-rediacc && go build -v ./...

  unit-test:
    runs-on: ubuntu-latest
    needs: build
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-go@v5
        with:
          go-version: '1.22'
      - run: cd packages/terraform/terraform-provider-rediacc && go test ./... -v

  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-go@v5
        with:
          go-version: '1.22'
      - uses: golangci/golangci-lint-action@v4
        with:
          working-directory: packages/terraform/terraform-provider-rediacc

  example-validation:
    runs-on: ubuntu-latest
    needs: build
    steps:
      - uses: actions/checkout@v4
      - uses: hashicorp/setup-terraform@v3
      - run: |
          cd packages/terraform/terraform-provider-rediacc
          make install
          for dir in examples/resources/*/; do
            cd "$dir"
            terraform init -backend=false
            terraform validate
            cd -
          done

  # Acceptance tests require self-hosted runner with KVM
  acceptance:
    runs-on: [self-hosted, kvm]
    needs: [unit-test, lint]
    timeout-minutes: 45
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-go@v5
        with:
          go-version: '1.22'
      - run: npm install && cd packages/shared && npm run build
      - name: Provision test VMs
        run: ./run.sh rdc ops up --basic --parallel
      - name: Register and setup machines
        run: |
          ./run.sh rdc config add-machine rediacc11 --ip 192.168.111.11 --user muhammed
          ./run.sh rdc config add-machine rediacc12 --ip 192.168.111.12 --user muhammed
          ./run.sh rdc config set-ssh \
            --private-key ~/.renet/staging/.ssh/id_rsa \
            --public-key ~/.renet/staging/.ssh/id_rsa.pub
          ./run.sh rdc config setup-machine rediacc11
          ./run.sh rdc config setup-machine rediacc12
      - name: Run acceptance tests
        run: |
          cd packages/terraform/terraform-provider-rediacc
          TF_ACC=1 RDC_BINARY="$(pwd)/../../../run.sh rdc" go test ./... -v -timeout 30m
      - name: Teardown VMs
        if: always()
        run: ./run.sh rdc ops down

  docs:
    runs-on: ubuntu-latest
    needs: build
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-go@v5
        with:
          go-version: '1.22'
      - run: |
          go install github.com/hashicorp/terraform-plugin-docs/cmd/tfplugindocs@latest
          cd packages/terraform/terraform-provider-rediacc
          tfplugindocs generate
          git diff --exit-code docs/ || (echo "Docs out of date" && exit 1)
```

---

## Test Sweepers

Acceptance tests that fail mid-run leave orphaned resources (test repos,
test machines in config). Implement test sweepers to clean up:

- Sweeper runs before each test suite
- Deletes any resources matching test prefixes (`acc-test-*`)
- Also runs after suite completion (in `TestMain`)
- Prevents resource accumulation across failed test runs

This pattern is used by the AWS and Google Terraform providers.

## What to Test Beyond CRUD

| Scenario | What it validates |
|----------|-------------------|
| **Idempotency** | Second `apply` produces no diff |
| **Import then plan** | Imported resource shows no drift |
| **Import block (TF 1.5+)** | `import { to = ... id = ... }` works without CLI |
| **for_each with map** | Resources work with `for_each` (not just `count`) |
| **Concurrent operations** | Two repos on different machines in same apply |
| **Timeout behavior** | Long operation respects configured timeout |
| **Error recovery** | Failed create doesn't leave partial state |
| **Config mutex** | Two machine creates don't corrupt config version |
| **Backup before destroy** | Destroy with `backup_before_destroy` actually backs up |
| **Drift detection** | Manual `rdc repo down` detected by next `terraform plan` |
| **No phantom diffs** | Computed attributes don't change between reads |
| **Env var fallback** | Provider works with `REDIACC_CONFIG_NAME` env var only |
| **Provider aliases** | Multiple provider instances target different configs |
| **Attribute-path errors** | Error messages reference the specific attribute that failed |

## Test Coverage Goals

| Layer | Target | What it validates |
|-------|--------|-------------------|
| Unit | 80%+ | Schema, state mapping, import parsing, client commands, envelope unwrapping |
| Acceptance | All resources + data sources | Full CRUD lifecycle, idempotency, import, drift |
| Examples | 100% | All example configs are valid HCL |
| Concurrency | Core resources | mutexKV prevents config corruption |
