import { useSearchParams } from 'react-router-dom'
import PriceChangeForm from './PriceChangeForm'

export default function PriceChangeNew() {
  const [searchParams] = useSearchParams()
  const editId = searchParams.get('edit')
  return <PriceChangeForm editId={editId ? parseInt(editId) : undefined} variant="business" />
}
