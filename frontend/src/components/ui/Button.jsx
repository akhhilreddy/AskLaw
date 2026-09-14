export default function Button({children,type="button",...props}){return <button type={type} {...props} className="primary-button">{children}</button>}
