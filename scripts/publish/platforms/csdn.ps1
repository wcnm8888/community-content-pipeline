function Invoke-CsdnPublish {
    param(
        [Parameter(Mandatory = $true)]$Context,
        [Parameter(Mandatory = $true)]$Pack
    )

    $spec = [pscustomobject]@{
        Key = "csdn"
        Url = "https://editor.csdn.net/md/"
        CoverRatio = "16:9"
        EntryHints = @("标题", "发布文章", "保存草稿", "标签", "摘要")
        ManualBeforeDraft = ""
        PreClickTexts = @()
        ImportMarkdown = $true
        ImportClickTexts = @("更多", "导入")
        SkipBodyFillAfterImport = $true
        OpenSettingsTexts = @("发布文章")
        CoverClickTexts = @("从本地上传", "上传封面", "添加封面", "添加文章封面")
        SaveDraftTexts = @()
        SaveOptional = $true
        PublishTexts = @("发布文章", "发布")
        Selectors = [pscustomobject]@{
            title = @(
                "input[placeholder*='标题']",
                "textarea[placeholder*='标题']",
                "#txtTitle"
            )
            body = @(
                ".bytemd-editor textarea",
                ".CodeMirror textarea",
                ".cm-content",
                "textarea[placeholder*='正文']",
                "#contentEditor textarea",
                "[contenteditable='true']"
            )
            summary = @(
                "textarea[placeholder*='摘要']",
                "textarea[placeholder*='文章摘要']",
                "input[placeholder*='摘要']"
            )
            topics = @()
            tags = @(
                "input[placeholder*='标签']",
                "input[placeholder*='添加标签']",
                "input[placeholder*='搜索标签']"
            )
            hashtags = @()
        }
    }

    Invoke-GenericPlatform $Context $spec $Pack
}
