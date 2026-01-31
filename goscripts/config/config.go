package config

import (
	"log"
	"log/slog"
	"os"
	"reflect"
	"sync"

	"github.com/knadh/koanf/parsers/toml"
	"github.com/knadh/koanf/providers/file"
	"github.com/knadh/koanf/providers/posflag"
	"github.com/knadh/koanf/v2"
	flag "github.com/spf13/pflag"
)

var (
	// C 全局配置单例
	C    *Config
	once sync.Once
	k    = koanf.New(".")
)

// Config 配置结构
type Config struct {
	Cmd          CmdConfg            `koanf:"cmd"`
	TencentCloud TencentCloundConfig `koanf:"tencent_cloud"`
}

type CmdConfg struct {
	Precache PrecacheConfg `koanf:"precache"`
}

type PrecacheConfg struct {
	Mode              string `koanf:"mode"`                // 预热模式: precache(默认), sandboxtool
	RoleArn           string `koanf:"role_arn"`            // 角色 ARN
	TCRRegistryID     string `koanf:"tcr_registry_id"`     // TCR 实例 ID
	TCRNamespace      string `koanf:"tcr_namespace"`       // TCR 命名空间
	TCRImageRegex     string `koanf:"tcr_image_regex"`     // 镜像过滤正则表达式
	ImageRegistryType string `koanf:"image_registry_type"` // 镜像仓库类型: enterprise(TCR), personal
	Concurrency       int    `koanf:"concurrency"`         // 并发数
	MaxRetries        int    `koanf:"max_retries"`         // 失败任务最大重试次数
	LogFile           string `koanf:"log_file"`            // 日志文件路径
}

// TencentCloundConfig 腾讯云 Agent Sandbox 配置
type TencentCloundConfig struct {
	Region    string    `koanf:"region"`
	SecretID  string    `koanf:"secret_id"`
	SecretKey string    `koanf:"secret_key"`
	AGS       AGSConfig `koanf:"ags"`
}

type AGSConfig struct {
	Mode string `koanf:"mode"`
}

// registerFlags 通过反射自动注册命令行参数
func registerFlags(f *flag.FlagSet, t reflect.Type, prefix string) {
	for i := 0; i < t.NumField(); i++ {
		field := t.Field(i)
		tag := field.Tag.Get("koanf")
		if tag == "" {
			tag = field.Name
		}

		key := tag
		if prefix != "" {
			key = prefix + "." + tag
		}

		switch field.Type.Kind() {
		case reflect.String:
			f.String(key, "", "")
		case reflect.Int, reflect.Int64:
			f.Int64(key, 0, "")
		case reflect.Bool:
			f.Bool(key, false, "")
		case reflect.Float64:
			f.Float64(key, 0, "")
		case reflect.Struct:
			registerFlags(f, field.Type, key)
		}
	}
}

// Init 初始化配置，优先级: 命令行 > 配置文件
func Init() {
	once.Do(func() {
		f := flag.NewFlagSet("config", flag.ContinueOnError)

		// 配置文件路径参数
		f.String("config", "config.toml", "配置文件路径")

		// 通过反射自动注册所有配置字段为命令行参数
		registerFlags(f, reflect.TypeOf(Config{}), "")

		// 解析命令行参数
		if err := f.Parse(os.Args[1:]); err != nil {
			log.Printf("解析命令行参数失败: %v", err)
		}

		// 1. 先加载配置文件（低优先级）
		configPath, _ := f.GetString("config")
		if configPath != "" {
			if err := k.Load(file.Provider(configPath), toml.Parser()); err != nil {
				log.Printf("加载配置文件失败: %v", err)
			}
		}

		// 2. 再加载命令行参数（高优先级，会覆盖配置文件）
		if err := k.Load(posflag.Provider(f, ".", k), nil); err != nil {
			log.Fatalf("加载命令行参数失败: %v", err)
		}

		// 解析到结构体
		C = &Config{}
		if err := k.Unmarshal("", C); err != nil {
			log.Fatalf("解析配置失败: %v", err)
		}

		slog.Info("配置初始化完成", "config", C)
	})
}
