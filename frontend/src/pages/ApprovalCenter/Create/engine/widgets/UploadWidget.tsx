import { InboxOutlined } from '@ant-design/icons'
import { Upload } from 'antd'
import { fileApi } from '../../../../../services/api'
import { registerWidget } from '../registry'
import type { WidgetProps } from '../types'

function UploadWidget({ field, fileList, onChange }: WidgetProps) {
  return (
    <Upload.Dragger multiple fileList={fileList || []}
      onChange={({ fileList: next }: any) => onChange?.(next)}
      customRequest={async (options: any) => {
        try {
          const res: any = await fileApi.upload(options.file, field.uploadNamespace || 'misc')
          options.onSuccess(res.data || res, options.file)
        } catch (e) { options.onError(e as any) }
      }}>
      <p className="ant-upload-drag-icon"><InboxOutlined /></p>
      <p className="ant-upload-text">点击或拖拽上传附件</p>
    </Upload.Dragger>
  )
}

registerWidget('upload', UploadWidget)
