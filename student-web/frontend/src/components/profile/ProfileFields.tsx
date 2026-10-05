import { useEffect, useId, useState } from 'react';
import { ApiError, apiGet } from '../../api/client';
import type { AddressPayload } from '../../types/student';

type Option = { code: string; name: string };
type Province = Option & { wards: Option[] };
export type ProfileOptions = {
  divisions: { provinces: Province[]; historicalProvinces: Option[]; provinceCheckedAt: string; wardEffectiveDate: string };
  countries: Option[]; ethnicities: string[]; religions: string[]; residenceRelations: string[];
};
let request: Promise<ProfileOptions> | undefined;
function load() {
  return request ??= apiGet<ProfileOptions>('/profile-options').catch(error => { request = undefined; throw error; });
}
export function useProfileOptions() {
  const [options, setOptions] = useState<ProfileOptions>();
  const [error, setError] = useState('');
  const [attempt, retry] = useState(0);
  useEffect(() => {
    let alive = true;
    setError('');
    load().then(data => { if (alive) { setOptions(data); setError(''); } })
      .catch((cause: unknown) => {
        if (!alive) return;
        const status = cause instanceof ApiError ? cause.status : undefined;
        const detail = status === 401 ? 'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.'
          : status === 403 || status === 404 ? 'API danh mục chưa khả dụng. Hãy kiểm tra backend đã chạy phiên bản mới và đăng nhập lại.'
          : status ? 'Vui lòng kiểm tra log backend rồi thử lại.'
          : 'Không kết nối được hoặc phản hồi không hợp lệ. Hãy kiểm tra backend và proxy /api.';
        setError(`Không tải được danh mục${status ? ` (HTTP ${status})` : ''}. ${detail}`);
      });
    return () => { alive = false; };
  }, [attempt]);
  return { options, error, retry: () => retry(n => n + 1) };
}
export function CatalogSelect({ label, value, options, onChange, disabled = false, placeholder = '— Chọn —' }:
  { label: string; value?: string | null; options: string[]; onChange: (value: string) => void; disabled?: boolean; placeholder?: string }) {
  const id = useId();
  const legacy = !!value && !options.includes(value);
  return <div className="profile-form-group form-group">
    <label htmlFor={id} className="profile-form-label form-label">{label}</label>
    <select id={id} className="profile-form-input form-select" value={value ?? ''} disabled={disabled} onChange={e => onChange(e.target.value)}>
      <option value="">{placeholder}</option>
      {legacy && <option value={value!}>{value} (đã lưu trước đây)</option>}
      {options.map(option => <option key={option} value={option}>{option}</option>)}
    </select>
    {legacy && <small>Giá trị cũ được giữ nguyên. Bạn có thể chọn lại từ danh mục.</small>}
  </div>;
}
export function CountrySelect({ label, value, countries, onChange }:
  { label: string; value: string; countries: Option[]; onChange: (value: string) => void }) {
  const id = useId();
  return <div className="profile-form-group form-group"><label htmlFor={id} className="profile-form-label form-label">{label}</label>
    <select id={id} className="profile-form-input form-select" value={value} disabled={!countries.length} onChange={e => onChange(e.target.value)}>
      <option value="VN">Việt Nam</option>
      {countries.filter(c => c.code !== 'VN').map(c => <option key={c.code} value={c.code}>{c.name}</option>)}
    </select></div>;
}
function canonicalProvince(value: string, provinces: Option[]) {
  return provinces.find(p => p.name === value || p.name.replace(/^(Thành phố|Tỉnh) /, '') === value)?.name ?? value;
}
export function ProvinceField({ label, value, countryCode, options, historical = false, onChange }:
  { label: string; value?: string | null; countryCode: string; options?: ProfileOptions; historical?: boolean; onChange: (value: string) => void }) {
  const id = useId();
  if (countryCode !== 'VN') return <div className="profile-form-group form-group"><label htmlFor={id} className="profile-form-label form-label">{label}</label>
    <input id={id} className="profile-form-input form-input" maxLength={100} value={value ?? ''} onChange={e => onChange(e.target.value)} placeholder="Nhập địa danh tại nước ngoài" /></div>;
  const provinces = [...(options?.divisions.provinces ?? []), ...(historical ? options?.divisions.historicalProvinces ?? [] : [])];
  return <CatalogSelect label={label} value={canonicalProvince(value ?? '', provinces)} options={[...new Set(provinces.map(p => p.name))]}
    onChange={onChange} disabled={!options} placeholder={options ? '— Chọn tỉnh/thành phố —' : 'Đang tải danh mục…'} />;
}
export function AddressLocationFields({ form, onChange }:
  { form: AddressPayload; onChange: (value: AddressPayload) => void }) {
  const { options, error, retry } = useProfileOptions();
  const country = form.countryCode ?? 'VN';
  const parent = options?.divisions.provinces.find(p => p.name === canonicalProvince(form.provinceCity ?? '', options.divisions.provinces));
  const wardId = useId();
  return <>
    {error && <div role="alert">{error} <button type="button" onClick={retry}>Thử lại</button></div>}
    <CountrySelect label="Quốc gia của địa chỉ" value={country} countries={options?.countries ?? []}
      onChange={countryCode => onChange({ ...form, countryCode, provinceCity: '', wardCommune: '' })} />
    <div className="profile-form-row form-row">
      <ProvinceField label="Tỉnh / Thành phố" value={form.provinceCity} countryCode={country} options={options}
        onChange={provinceCity => onChange({ ...form, provinceCity, wardCommune: '' })} />
      {country === 'VN' ? <CatalogSelect label="Xã / Phường / Đặc khu" value={form.wardCommune} options={parent?.wards.map(w => w.name) ?? []}
        disabled={!parent} placeholder={parent ? '— Chọn xã/phường/đặc khu —' : 'Chọn tỉnh/thành phố trước'}
        onChange={wardCommune => onChange({ ...form, wardCommune })} />
        : <div className="profile-form-group form-group"><label htmlFor={wardId} className="profile-form-label form-label">Đơn vị địa phương</label>
          <input id={wardId} className="profile-form-input form-input" maxLength={100} value={form.wardCommune ?? ''}
            onChange={e => onChange({ ...form, wardCommune: e.target.value })} /></div>}
    </div>
    <CatalogSelect label="Quan hệ với nơi ở" value={form.residenceRelation} options={options?.residenceRelations ?? []}
      disabled={!options} onChange={residenceRelation => onChange({ ...form, residenceRelation })} />
  </>;
}

export function countryLabel(code?: string) {
  if (!code || code === 'VN') return 'Việt Nam';
  return new Intl.DisplayNames(['vi'], { type: 'region' }).of(code) ?? code;
}
