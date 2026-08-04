// Command license-mint forges repo-license blobs for the licensing enforcement
// battery (.ci/scripts/private/license-e2e.sh).
//
// It deliberately imports renet's REAL github.com/rediacc/renet/pkg/license and
// .../pkg/subscription packages rather than re-encoding the wire format by hand.
// The payload shape, the key fingerprint algorithm, the delegation-cert struct
// and the chain-hash formula therefore cannot drift from the verifier: a change
// to any of them breaks this tool's compile or its output at the same moment it
// breaks renet, instead of silently turning the battery green against a format
// nothing else speaks.
//
// It mints licenses signed by the master key directly, licenses signed by a
// delegated key plus a master-signed delegation cert, and every deliberately
// broken variant the battery needs (stranger signer, stranger cert signer,
// forged publicKeyId, wrong machine, past expiry, regressed sequence).
//
// Signing contract (pkg/license/validator.go:37-53): the payload is the base64
// of the license JSON, and the signature is over the BASE64 PAYLOAD STRING's
// bytes, not over the decoded JSON.
package main

import (
	"crypto/ed25519"
	"crypto/rand"
	"crypto/x509"
	"encoding/base64"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/rediacc/renet/pkg/license"
	"github.com/rediacc/renet/pkg/subscription"
)

func main() {
	if err := run(); err != nil {
		fmt.Fprintf(os.Stderr, "license-mint: %v\n", err)
		os.Exit(1)
	}
}

type config struct {
	genKey         bool
	printMachineID bool

	masterKey string
	outDir    string

	repo         string
	machine      string
	subscription string
	plan         string
	kind         string
	status       string
	maxSizeGb    int

	issuedAt      string
	refreshAt     string
	hardExpires   string
	sequence      int
	prevChainHash string
	chainHash     bool

	delegate       bool
	delegateKey    string
	certSigner     string
	certValidFrom  string
	certValidUntil string
	certMaxSizeGb  int
	certMaxIssues  int

	forgeSigner string
	keyID       string

	datastoreID        string
	renewalURL         string
	storageFingerprint string
}

func run() error {
	var cfg config
	flag.BoolVar(&cfg.genKey, "gen-key", false,
		"print a fresh Ed25519 keypair as JSON {private,public} (base64 PKCS8 / SPKI, byte-identical to .ci/scripts/infra/ci-env.sh) and exit")
	flag.BoolVar(&cfg.printMachineID, "print-machine-id", false,
		"print this machine's license.GetMachineID() and exit")

	flag.StringVar(&cfg.masterKey, "master-key", "", "base64 PKCS8 Ed25519 private key of the baked master key (required to mint)")
	flag.StringVar(&cfg.outDir, "out-dir", "", "directory to write <publicKeyId>.json into (required to mint)")

	flag.StringVar(&cfg.repo, "repo", "", "repositoryGuid the license is bound to (required to mint)")
	flag.StringVar(&cfg.machine, "machine", "auto", "machineId to bind: 'auto' for this machine, else a literal")
	flag.StringVar(&cfg.subscription, "subscription", "sub-license-e2e", "subscriptionId (also the chain-state scope)")
	flag.StringVar(&cfg.plan, "plan", "PROFESSIONAL", "planCode")
	flag.StringVar(&cfg.kind, "kind", "primary", "kind")
	flag.StringVar(&cfg.status, "status", "ACTIVE", "status")
	flag.IntVar(&cfg.maxSizeGb, "max-size-gb", 100, "maxRepositorySizeGb")

	flag.StringVar(&cfg.issuedAt, "issued-at", "-1h", "issuedAt as a Go duration offset from now")
	flag.StringVar(&cfg.refreshAt, "refresh-at", "360h", "refreshRecommendedAt as a Go duration offset from now")
	flag.StringVar(&cfg.hardExpires, "hard-expires", "720h", "hardExpiresAt as a Go duration offset from now (negative = already expired)")
	flag.IntVar(&cfg.sequence, "sequence", 0, "sequence (chain validation only runs when > 0)")
	flag.StringVar(&cfg.prevChainHash, "prev-chain-hash", "", "prevChainHash")
	flag.BoolVar(&cfg.chainHash, "chain-hash", false, "compute and set the blob's chainHash from prevChainHash + payload")

	flag.BoolVar(&cfg.delegate, "delegate", false, "sign the license with a delegated key and attach a delegation cert")
	flag.StringVar(&cfg.delegateKey, "delegate-key", "", "base64 PKCS8 delegated private key (default: generate a fresh one)")
	flag.StringVar(&cfg.certSigner, "cert-signer", "", "base64 PKCS8 key that signs the delegation cert (default: the master key)")
	flag.StringVar(&cfg.certValidFrom, "cert-valid-from", "-1h", "cert validFrom as a Go duration offset from now")
	flag.StringVar(&cfg.certValidUntil, "cert-valid-until", "720h", "cert validUntil as a Go duration offset from now")
	flag.IntVar(&cfg.certMaxSizeGb, "cert-max-size-gb", -1, "cert maxRepositorySizeGb (-1 = unlimited)")
	flag.IntVar(&cfg.certMaxIssues, "cert-max-issuances", -1, "cert maxTotalIssuances (-1 = unlimited)")

	flag.StringVar(&cfg.forgeSigner, "forge-signer", "", "base64 PKCS8 key that produces the license SIGNATURE, while publicKeyId still names the nominal signer (forges a stranger-signed blob)")
	flag.StringVar(&cfg.keyID, "key-id", "", "override the blob's publicKeyId (and therefore the output filename)")

	flag.StringVar(&cfg.datastoreID, "datastore-id", "",
		"bind the license to a datastore identity (payload datastoreId); empty = unbound, which is what a pre-binding license looks like")
	flag.StringVar(&cfg.renewalURL, "renewal-url", "",
		"stamp the self-renewal endpoint into the payload (payload renewalUrl)")
	flag.StringVar(&cfg.storageFingerprint, "storage-fingerprint", "",
		"bind the license to a repo path's storage fingerprint; the literal value, or 'auto:<path>' to compute it the way the scan does")
	flag.Parse()

	switch {
	case cfg.genKey:
		return printGeneratedKey()
	case cfg.printMachineID:
		id, err := license.GetMachineID()
		if err != nil {
			return err
		}
		fmt.Println(id)
		return nil
	}
	return mint(cfg)
}

func printGeneratedKey() error {
	pub, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		return err
	}
	privB64, err := encodePrivate(priv)
	if err != nil {
		return err
	}
	pubB64, err := encodePublic(pub)
	if err != nil {
		return err
	}
	return json.NewEncoder(os.Stdout).Encode(map[string]string{"private": privB64, "public": pubB64})
}

func mint(cfg config) error {
	if cfg.masterKey == "" {
		return errors.New("-master-key is required")
	}
	if cfg.outDir == "" {
		return errors.New("-out-dir is required")
	}
	if cfg.repo == "" {
		return errors.New("-repo is required")
	}

	master, err := parsePrivate(cfg.masterKey)
	if err != nil {
		return fmt.Errorf("master key: %w", err)
	}

	// The key whose fingerprint the blob claims, and whose signature it should
	// carry unless -forge-signer overrides the latter.
	signer := master
	var cert *subscription.SignedDelegationCert
	if cfg.delegate {
		signer, cert, err = buildDelegation(cfg, master)
		if err != nil {
			return err
		}
	}

	machineID := cfg.machine
	if machineID == "auto" {
		if machineID, err = license.GetMachineID(); err != nil {
			return err
		}
	}

	now := time.Now()
	issuedAt, err := offset(now, cfg.issuedAt)
	if err != nil {
		return fmt.Errorf("-issued-at: %w", err)
	}
	refreshAt, err := offset(now, cfg.refreshAt)
	if err != nil {
		return fmt.Errorf("-refresh-at: %w", err)
	}
	hardExpires, err := offset(now, cfg.hardExpires)
	if err != nil {
		return fmt.Errorf("-hard-expires: %w", err)
	}

	storageFingerprint, err := resolveStorageFingerprint(cfg.storageFingerprint)
	if err != nil {
		return err
	}

	payloadJSON, err := json.Marshal(license.RepoLicense{
		Version:              1,
		SubscriptionID:       cfg.subscription,
		MachineID:            machineID,
		ClientMachineID:      machineID,
		RepositoryGuid:       cfg.repo,
		Kind:                 cfg.kind,
		PlanCode:             cfg.plan,
		Status:               cfg.status,
		MaxRepositorySizeGb:  cfg.maxSizeGb,
		DatastoreID:          cfg.datastoreID,
		RenewalURL:           cfg.renewalURL,
		StorageFingerprint:   storageFingerprint,
		IssuedAt:             issuedAt,
		RefreshRecommendedAt: refreshAt,
		HardExpiresAt:        hardExpires,
		Sequence:             cfg.sequence,
		PrevChainHash:        cfg.prevChainHash,
		IssuedByEmail:        "license-e2e@rediacc.invalid",
		CompanyName:          "license-e2e",
	})
	if err != nil {
		return err
	}
	payload := base64.StdEncoding.EncodeToString(payloadJSON)

	// publicKeyId names the key a verifier must use. -forge-signer keeps that
	// claim while signing with a different key, which is exactly the shape of a
	// stranger-signed blob dropped into a repo's license directory.
	signingKey := signer
	if cfg.forgeSigner != "" {
		if signingKey, err = parsePrivate(cfg.forgeSigner); err != nil {
			return fmt.Errorf("forge signer: %w", err)
		}
	}

	keyID := cfg.keyID
	if keyID == "" {
		keyID = subscription.KeyFingerprint(publicOf(signer))
	}

	blob := license.SignedRepoLicense{
		Payload:        payload,
		Signature:      sign(signingKey, payload),
		PublicKeyID:    keyID,
		DelegationCert: cert,
	}
	if cfg.chainHash {
		blob.ChainHash = subscription.ComputeChainHash(cfg.prevChainHash, payload)
	}

	if err := os.MkdirAll(cfg.outDir, 0o755); err != nil {
		return err
	}
	path := filepath.Join(cfg.outDir, keyID+".json")
	data, err := json.MarshalIndent(blob, "", "  ")
	if err != nil {
		return err
	}
	// 0644: the battery installs licenses as root but drives renet unprivileged,
	// mirroring how a real install is readable by every renet invocation.
	if err := os.WriteFile(path, data, 0o644); err != nil {
		return err
	}

	return json.NewEncoder(os.Stdout).Encode(map[string]string{
		"path":        path,
		"publicKeyId": keyID,
		"machineId":   machineID,
		"chainHash":   blob.ChainHash,
	})
}

// resolveStorageFingerprint turns the -storage-fingerprint flag into a payload
// value. `auto:<path>` computes it with license.StorageFingerprint, which is the
// SAME function the scan mints with and the validators check with. Computing it
// here by hand would recreate exactly the mint/check skew that made the check
// dormant in the first place.
func resolveStorageFingerprint(value string) (string, error) {
	const autoPrefix = "auto:"
	if !strings.HasPrefix(value, autoPrefix) {
		return value, nil
	}
	path := strings.TrimPrefix(value, autoPrefix)
	info, err := os.Stat(path)
	if err != nil {
		return "", fmt.Errorf("-storage-fingerprint auto: %w", err)
	}
	return license.StorageFingerprint(info), nil
}

// buildDelegation returns the delegated signing key plus the cert that
// authorizes it. -cert-signer lets the battery hand the cert to a stranger key,
// which the verifier must reject before it ever looks at the license itself.
func buildDelegation(cfg config, master ed25519.PrivateKey) (ed25519.PrivateKey, *subscription.SignedDelegationCert, error) {
	delegated := ed25519.PrivateKey(nil)
	if cfg.delegateKey != "" {
		parsed, err := parsePrivate(cfg.delegateKey)
		if err != nil {
			return nil, nil, fmt.Errorf("delegate key: %w", err)
		}
		delegated = parsed
	} else {
		_, generated, err := ed25519.GenerateKey(rand.Reader)
		if err != nil {
			return nil, nil, err
		}
		delegated = generated
	}

	certSigner := master
	if cfg.certSigner != "" {
		parsed, err := parsePrivate(cfg.certSigner)
		if err != nil {
			return nil, nil, fmt.Errorf("cert signer: %w", err)
		}
		certSigner = parsed
	}

	now := time.Now()
	validFrom, err := offset(now, cfg.certValidFrom)
	if err != nil {
		return nil, nil, fmt.Errorf("-cert-valid-from: %w", err)
	}
	validUntil, err := offset(now, cfg.certValidUntil)
	if err != nil {
		return nil, nil, fmt.Errorf("-cert-valid-until: %w", err)
	}

	delegatedPub, err := encodePublic(publicOf(delegated))
	if err != nil {
		return nil, nil, err
	}
	certJSON, err := json.Marshal(subscription.DelegationCert{
		Version:             1,
		SubscriptionID:      cfg.subscription,
		PlanCode:            subscription.PlanCode(cfg.plan),
		MaxMachines:         -1,
		MaxRepositorySizeGb: cfg.certMaxSizeGb,
		MaxTotalIssuances:   cfg.certMaxIssues,
		DelegatedPublicKey:  delegatedPub,
		ValidFrom:           validFrom.Format(time.RFC3339),
		ValidUntil:          validUntil.Format(time.RFC3339),
		IssuedAt:            now.Format(time.RFC3339),
	})
	if err != nil {
		return nil, nil, err
	}
	certPayload := base64.StdEncoding.EncodeToString(certJSON)

	return delegated, &subscription.SignedDelegationCert{
		Payload:     certPayload,
		Signature:   sign(certSigner, certPayload),
		PublicKeyID: subscription.KeyFingerprint(publicOf(certSigner)),
	}, nil
}

// sign produces the signature the verifier checks: Ed25519 over the bytes of
// the BASE64 payload string (validator.go:42), not over the decoded JSON.
func sign(key ed25519.PrivateKey, payload string) string {
	return base64.StdEncoding.EncodeToString(ed25519.Sign(key, []byte(payload)))
}

func publicOf(key ed25519.PrivateKey) ed25519.PublicKey {
	return key.Public().(ed25519.PublicKey)
}

func parsePrivate(b64 string) (ed25519.PrivateKey, error) {
	der, err := base64.StdEncoding.DecodeString(b64)
	if err != nil {
		return nil, fmt.Errorf("not base64: %w", err)
	}
	parsed, err := x509.ParsePKCS8PrivateKey(der)
	if err != nil {
		return nil, fmt.Errorf("not a PKCS8 key: %w", err)
	}
	key, ok := parsed.(ed25519.PrivateKey)
	if !ok {
		return nil, fmt.Errorf("not an Ed25519 key: %T", parsed)
	}
	return key, nil
}

func encodePrivate(key ed25519.PrivateKey) (string, error) {
	der, err := x509.MarshalPKCS8PrivateKey(key)
	if err != nil {
		return "", err
	}
	return base64.StdEncoding.EncodeToString(der), nil
}

func encodePublic(key ed25519.PublicKey) (string, error) {
	der, err := x509.MarshalPKIXPublicKey(key)
	if err != nil {
		return "", err
	}
	return base64.StdEncoding.EncodeToString(der), nil
}

func offset(now time.Time, value string) (time.Time, error) {
	duration, err := time.ParseDuration(value)
	if err != nil {
		return time.Time{}, err
	}
	return now.Add(duration), nil
}
