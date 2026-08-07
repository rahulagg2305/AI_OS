{{/*
Standard Helm naming helpers — the release name prefixes every real
resource this chart creates, so two installs never collide.
*/}}

{{- define "ai-os.fullname" -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "ai-os.labels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end -}}

{{- define "ai-os.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{ .Values.serviceAccount.name | default (include "ai-os.fullname" .) }}
{{- else -}}
{{ .Values.serviceAccount.name }}
{{- end -}}
{{- end -}}
