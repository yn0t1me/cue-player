export default function CollectionFields({ name, description, onName, onDescription, disabled = false }: {
  name: string; description: string; onName: (value: string) => void;
  onDescription: (value: string) => void; disabled?: boolean;
}) {
  return <div className="collection-fields"><label>合集名称<input value={name} maxLength={200} required
    disabled={disabled} onChange={event => onName(event.target.value)} /></label>
    <label>简介（选填）<textarea value={description} maxLength={2000} disabled={disabled}
      onChange={event => onDescription(event.target.value)} /></label></div>;
}
