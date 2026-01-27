package xk6ags

import (
	"os"
	"strings"

	"github.com/tencentcloud/tencentcloud-sdk-go/tencentcloud/common"
	"github.com/tencentcloud/tencentcloud-sdk-go/tencentcloud/common/profile"
	"go.k6.io/k6/js/modules"

	ags "github.com/tencentcloud/tencentcloud-sdk-go/tencentcloud/ags/v20250920"
)

func init() {
	modules.Register("k6/x/ags", new(RootModule))
}

// RootModule is the global module instance that will create AGS instances for each VU.
type RootModule struct{}

// AGS is the per-VU module instance.
type AGS struct {
	vu                    modules.VU
	client                *ags.Client
	secretID              string
	secretKey             string
	region                string
	host                  string
	dataPlaneDomainSuffix string
	tokenManager          *tokenManager
}

// Exports implements modules.Instance.
func (m *AGS) Exports() modules.Exports {
	return modules.Exports{
		Default: m,
		Named: map[string]any{
			// 控制面
			"startSandboxInstance":              m.StartSandboxInstance,
			"stopSandboxInstance":               m.StopSandboxInstance,
			"startSandboxInstanceWithAsyncStop": m.StartSandboxInstanceWithAsyncStop,
			"getAsyncStopPendingCount":          m.GetAsyncStopPendingCount,
			"getAsyncStopResults":               m.GetAsyncStopResults,
			// 数据面 HTTP
			"get":    m.Get,
			"post":   m.Post,
			"put":    m.Put,
			"delete": m.Delete,
			"patch":  m.Patch,
			// shell2http with stress-ng
			"execShell2Http":             m.ExecShell2Http,
			"runAsyncStress":             m.RunAsyncStress,
			"getAsyncStressPendingCount": m.GetAsyncStressPendingCount,
			"getAsyncStressResults":      m.GetAsyncStressResults,
		},
	}
}

func (m *RootModule) NewModuleInstance(vu modules.VU) modules.Instance {
	tencentcloudSecretID := strings.TrimSpace(os.Getenv("TENCENTCLOUD_SECRET_ID"))
	tencentcloudSecretKey := strings.TrimSpace(os.Getenv("TENCENTCLOUD_SECRET_KEY"))
	tencentcloudRegion := strings.TrimSpace(os.Getenv("TENCENTCLOUD_REGION"))
	if tencentcloudRegion == "" {
		tencentcloudRegion = "ap-guangzhou"
	}
	host := strings.TrimSpace(os.Getenv("AGS_HOST"))
	if host == "" {
		host = "ags.tencentcloudapi.com"
	}
	dataPlaneDomainSuffix := strings.TrimSpace(os.Getenv("AGS_DATA_PLANE_DOMAIN_SUFFIX"))
	if dataPlaneDomainSuffix == "" {
		dataPlaneDomainSuffix = "tencentags.com"
	}

	cred := common.NewCredential(tencentcloudSecretID, tencentcloudSecretKey)

	cpf := profile.NewClientProfile()
	cpf.HttpProfile.Endpoint = host

	client, _ := ags.NewClient(cred, tencentcloudRegion, cpf)

	agsInstance := &AGS{
		vu:                    vu,
		client:                client,
		secretID:              tencentcloudSecretID,
		secretKey:             tencentcloudSecretKey,
		region:                tencentcloudRegion,
		host:                  host,
		dataPlaneDomainSuffix: dataPlaneDomainSuffix,
	}
	agsInstance.tokenManager = newTokenManager(agsInstance)

	return agsInstance
}
