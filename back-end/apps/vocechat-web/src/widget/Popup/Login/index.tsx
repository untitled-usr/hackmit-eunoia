import { FormEvent, useEffect } from "react";
import { toast } from "react-hot-toast";
import { useDispatch } from "react-redux";

import { KEY_UID } from "@/app/config";
import { useRegisterMutation } from "../../../app/services/auth";
import { setAuthData } from "../../../app/slices/auth.data";
import StyledButton from "../../../components/styled/Button";
import { useWidget } from "../../WidgetContext";
import Loading from "@/components/Loading";
import { WIDGET_USER_PWD } from "@/app/config";

const randomText = () => (Math.random() + 1).toString(36).substring(7);

const Login = () => {
  const dispatch = useDispatch();
  const { autoReg, id } = useWidget();
  const [register, { isLoading, isSuccess, data, error }] = useRegisterMutation();

  const registerUser = () => {
    register({
      widget_id: id,
      password: WIDGET_USER_PWD,
      gender: 0,
      language: "en-US"
    });
  };

  const handleSubmit = (evt: FormEvent<HTMLFormElement>) => {
    evt.preventDefault();
    registerUser();
  };

  useEffect(() => {
    if (autoReg) {
      registerUser();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoReg]);

  useEffect(() => {
    if (isSuccess && data) {
      localStorage.setItem(KEY_UID, `${data.uid}`);
      dispatch(setAuthData({ user: data }));
    }
  }, [isSuccess, data, dispatch]);

  useEffect(() => {
    if (error) {
      toast.error("Something error!");
    }
  }, [error]);

  if (isLoading) return <Loading />;
  return (
    <div className="w-full h-full overflow-y-scroll py-6 px-4">
      <h2 className="text-xl font-semibold mb-4 text-center">Register</h2>
      <p className="text-sm text-gray-500 text-center mb-4">
        A new user id will be created on the server (name will match your uid).
      </p>
      <form className="flex flex-col gap-3" onSubmit={handleSubmit}>
        <StyledButton className="small" type="submit">
          Create account
        </StyledButton>
      </form>
    </div>
  );
};

export default Login;
